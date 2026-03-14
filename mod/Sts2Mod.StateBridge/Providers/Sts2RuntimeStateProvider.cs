using Sts2Mod.StateBridge.Configuration;
using Sts2Mod.StateBridge.Contracts;
using Sts2Mod.StateBridge.Core;
using Sts2Mod.StateBridge.Extraction;

namespace Sts2Mod.StateBridge.Providers;

public sealed class Sts2RuntimeStateProvider : IGameStateProvider
{
    private readonly BridgeOptions _options;
    private readonly Sts2RuntimeReflectionReader _reader;
    private readonly BridgeSessionState _sessionState;
    private readonly Dictionary<string, IWindowExtractor> _extractors;

    public Sts2RuntimeStateProvider(BridgeOptions options, InstallationProbeResult probe)
    {
        _options = options;
        _reader = new Sts2RuntimeReflectionReader(options, probe);
        _sessionState = new BridgeSessionState(options);
        _extractors = new IWindowExtractor[]
        {
            new CombatWindowExtractor(),
            new RewardWindowExtractor(),
            new MapWindowExtractor(),
            new MenuWindowExtractor(),
            new TerminalWindowExtractor(),
        }.ToDictionary(extractor => extractor.Phase, StringComparer.OrdinalIgnoreCase);
    }

    public HealthResponse GetHealth()
    {
        var status = _reader.GetStatusReport();
        return new HealthResponse(
            Healthy: status.Healthy,
            ProtocolVersion: _options.ProtocolVersion,
            ModVersion: _options.ModVersion,
            GameVersion: _options.GameVersion,
            ProviderMode: _options.ProviderMode,
            ReadOnly: _options.ReadOnly,
            Status: status.Status);
    }

    public DecisionSnapshot GetSnapshot(string? requestedPhase = null)
    {
        if (InGameRuntimeCoordinator.TryGetCurrentWindow(out var window, out _))
        {
            return window.Snapshot;
        }

        return Export().Snapshot;
    }

    public IReadOnlyList<LegalAction> GetActions(string? requestedPhase = null)
    {
        if (InGameRuntimeCoordinator.TryGetCurrentWindow(out var window, out _))
        {
            return window.Actions;
        }

        return Export().Actions;
    }

    public ActionResponse ApplyAction(ActionRequest request)
    {
        if (!InGameRuntimeCoordinator.IsInitialized)
        {
            return new ActionResponse(
                RequestId: request.RequestId ?? Guid.NewGuid().ToString("N"),
                DecisionId: request.DecisionId,
                ActionId: request.ActionId,
                Status: "rejected",
                ErrorCode: "not_in_game_runtime",
                Message: "Action execution is only available when the bridge is running inside the STS2 process.",
                Metadata: new Dictionary<string, object?>());
        }

        return InGameRuntimeCoordinator.ApplyAction(request, _options.ReadOnly);
    }

    public void EnableInGameRuntime(Logging.IBridgeLogger logger)
    {
        InGameRuntimeCoordinator.Initialize(_reader, _options, logger);
    }

    private ExportedWindow Export()
    {
        var context = _reader.CaptureWindow();
        return _extractors[context.Phase].Export(context, _sessionState);
    }
}
