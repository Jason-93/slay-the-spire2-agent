using Sts2Mod.StateBridge.Configuration;
using Sts2Mod.StateBridge.Contracts;
using Sts2Mod.StateBridge.Core;
using Sts2Mod.StateBridge.Extraction;
using Sts2Mod.StateBridge.Logging;

namespace Sts2Mod.StateBridge.Providers;

internal static class InGameRuntimeCoordinator
{
    private static readonly object Gate = new();
    private static readonly Queue<PendingAction> PendingActions = new();
    private static Sts2RuntimeReflectionReader? _reader;
    private static BridgeSessionState? _sessionState;
    private static Dictionary<string, IWindowExtractor>? _extractors;
    private static IBridgeLogger? _logger;
    private static ExportedWindow? _currentWindow;
    private static string? _lastTickError;
    private static bool _initialized;

    public static bool IsInitialized
    {
        get
        {
            lock (Gate)
            {
                return _initialized;
            }
        }
    }

    public static void Initialize(Sts2RuntimeReflectionReader reader, BridgeOptions options, IBridgeLogger logger)
    {
        lock (Gate)
        {
            if (_initialized)
            {
                return;
            }

            _reader = reader;
            _logger = logger;
            _sessionState = new BridgeSessionState(options);
            _extractors = new IWindowExtractor[]
            {
                new CombatWindowExtractor(),
                new RewardWindowExtractor(),
                new MapWindowExtractor(),
                new TerminalWindowExtractor(),
            }.ToDictionary(extractor => extractor.Phase, StringComparer.OrdinalIgnoreCase);
            _initialized = true;
            _lastTickError = null;
            _currentWindow = null;
            logger.Info("Initialized in-game runtime coordinator");
        }
    }

    public static void Shutdown()
    {
        lock (Gate)
        {
            while (PendingActions.Count > 0)
            {
                var pending = PendingActions.Dequeue();
                pending.Completion.TrySetResult(CreateFailedResponse(
                    pending.Request,
                    pending.Request.ActionId,
                    "bridge_shutdown",
                    "In-game runtime coordinator is shutting down."));
            }

            _currentWindow = null;
            _lastTickError = null;
            _extractors = null;
            _reader = null;
            _sessionState = null;
            _initialized = false;
        }
    }

    public static void Tick()
    {
        Sts2RuntimeReflectionReader? reader;
        BridgeSessionState? sessionState;
        Dictionary<string, IWindowExtractor>? extractors;
        IBridgeLogger? logger;
        lock (Gate)
        {
            if (!_initialized)
            {
                return;
            }

            reader = _reader;
            sessionState = _sessionState;
            extractors = _extractors;
            logger = _logger;
        }

        if (reader is null || sessionState is null || extractors is null)
        {
            return;
        }

        try
        {
            var context = reader.CaptureWindow();
            var window = extractors[context.Phase].Export(context, sessionState);
            lock (Gate)
            {
                _currentWindow = window;
                _lastTickError = null;
            }
        }
        catch (Exception ex)
        {
            lock (Gate)
            {
                _lastTickError = ex.Message;
            }

            logger?.Warn($"In-game tick could not capture runtime window: {ex.Message}");
        }

        ProcessPendingActions(reader, logger);
    }

    public static bool TryGetCurrentWindow(out ExportedWindow window, out string? error)
    {
        lock (Gate)
        {
            if (_currentWindow is not null)
            {
                window = _currentWindow;
                error = null;
                return true;
            }

            window = default!;
            error = _lastTickError ?? "In-game runtime window is not ready yet.";
            return false;
        }
    }

    public static ActionResponse ApplyAction(ActionRequest request, bool readOnly)
    {
        if (readOnly)
        {
            return CreateRejectedResponse(request, request.ActionId, "read_only", "Bridge is running in read-only mode.");
        }

        PendingAction pending;
        lock (Gate)
        {
            if (!_initialized)
            {
                return CreateRejectedResponse(request, request.ActionId, "not_in_game_runtime", "Bridge is not running inside the STS2 process.");
            }

            pending = new PendingAction(request);
            PendingActions.Enqueue(pending);
        }

        if (!pending.Completion.Task.Wait(TimeSpan.FromSeconds(2)))
        {
            return CreateFailedResponse(request, request.ActionId, "action_timeout", "Timed out waiting for the game thread to process the action.");
        }

        return pending.Completion.Task.GetAwaiter().GetResult();
    }

    private static void ProcessPendingActions(Sts2RuntimeReflectionReader reader, IBridgeLogger? logger)
    {
        while (true)
        {
            PendingAction? pending;
            ExportedWindow? window;
            lock (Gate)
            {
                if (PendingActions.Count == 0)
                {
                    return;
                }

                pending = PendingActions.Dequeue();
                window = _currentWindow;
            }

            try
            {
                var response = ExecutePendingAction(reader, pending.Request, window);
                pending.Completion.TrySetResult(response);
            }
            catch (Exception ex)
            {
                logger?.Error("Failed to process queued in-game action", ex);
                pending.Completion.TrySetResult(CreateFailedResponse(
                    pending.Request,
                    pending.Request.ActionId,
                    "action_execution_failed",
                    ex.Message));
            }
        }
    }

    private static ActionResponse ExecutePendingAction(
        Sts2RuntimeReflectionReader reader,
        ActionRequest request,
        ExportedWindow? currentWindow)
    {
        if (currentWindow is null)
        {
            return CreateRejectedResponse(request, request.ActionId, "runtime_not_ready", "No live decision window is available yet.");
        }

        if (!string.Equals(request.DecisionId, currentWindow.Snapshot.DecisionId, StringComparison.Ordinal))
        {
            return CreateRejectedResponse(request, request.ActionId, "stale_decision", "Requested decision_id is no longer current.");
        }

        var action = ResolveAction(currentWindow.Actions, request);
        if (action is null)
        {
            return CreateRejectedResponse(request, request.ActionId, "illegal_action", "Requested action is not part of the current legal action set.");
        }

        var result = reader.ExecuteAction(request, action);
        if (!result.Accepted)
        {
            return CreateRejectedResponse(request, action.ActionId, result.ErrorCode ?? "action_rejected", result.Message);
        }

        var metadata = new Dictionary<string, object?>(result.Metadata)
        {
            ["phase"] = currentWindow.Snapshot.Phase,
            ["state_version"] = currentWindow.Snapshot.StateVersion,
        };
        return CreateAcceptedResponse(request, action.ActionId, result.Message, metadata);
    }

    private static LegalAction? ResolveAction(IEnumerable<LegalAction> actions, ActionRequest request)
    {
        if (!string.IsNullOrWhiteSpace(request.ActionId))
        {
            return actions.FirstOrDefault(action => string.Equals(action.ActionId, request.ActionId, StringComparison.Ordinal));
        }

        return actions.FirstOrDefault(action =>
            string.Equals(action.Type, request.ActionType, StringComparison.OrdinalIgnoreCase) &&
            request.Params.All(pair => action.Params.TryGetValue(pair.Key, out var value) && Equals(value, pair.Value)));
    }

    private static ActionResponse CreateAcceptedResponse(
        ActionRequest request,
        string? actionId,
        string message,
        IReadOnlyDictionary<string, object?> metadata)
    {
        return new ActionResponse(
            RequestId: request.RequestId ?? Guid.NewGuid().ToString("N"),
            DecisionId: request.DecisionId,
            ActionId: actionId,
            Status: "accepted",
            ErrorCode: null,
            Message: message,
            Metadata: metadata);
    }

    private static ActionResponse CreateRejectedResponse(
        ActionRequest request,
        string? actionId,
        string errorCode,
        string message)
    {
        return new ActionResponse(
            RequestId: request.RequestId ?? Guid.NewGuid().ToString("N"),
            DecisionId: request.DecisionId,
            ActionId: actionId,
            Status: "rejected",
            ErrorCode: errorCode,
            Message: message,
            Metadata: new Dictionary<string, object?>());
    }

    private static ActionResponse CreateFailedResponse(
        ActionRequest request,
        string? actionId,
        string errorCode,
        string message)
    {
        return new ActionResponse(
            RequestId: request.RequestId ?? Guid.NewGuid().ToString("N"),
            DecisionId: request.DecisionId,
            ActionId: actionId,
            Status: "failed",
            ErrorCode: errorCode,
            Message: message,
            Metadata: new Dictionary<string, object?>());
    }

    private sealed class PendingAction
    {
        public PendingAction(ActionRequest request)
        {
            Request = request;
            Completion = new TaskCompletionSource<ActionResponse>(TaskCreationOptions.RunContinuationsAsynchronously);
        }

        public ActionRequest Request { get; }

        public TaskCompletionSource<ActionResponse> Completion { get; }
    }
}
