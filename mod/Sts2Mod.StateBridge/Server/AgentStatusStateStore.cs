using Sts2Mod.StateBridge.Contracts;

namespace Sts2Mod.StateBridge.Server;

internal static class AgentStatusStateStore
{
    private static readonly object Gate = new();
    private static readonly TimeSpan StaleTtl = TimeSpan.FromSeconds(5);
    private const int HistoryLimit = 12;
    private static StoredAgentStatus? _current;
    private static readonly List<StoredAgentStatus> History = [];

    public static bool TryValidate(AgentStatusUpdateRequest? request, out string message)
    {
        if (request is null)
        {
            message = "Request body is required.";
            return false;
        }

        if (string.IsNullOrWhiteSpace(request.SessionId))
        {
            message = "agent_status.session_id is required.";
            return false;
        }

        if (string.IsNullOrWhiteSpace(request.Phase))
        {
            message = "agent_status.phase is required.";
            return false;
        }

        if (string.IsNullOrWhiteSpace(request.Status))
        {
            message = "agent_status.status is required.";
            return false;
        }

        if (string.IsNullOrWhiteSpace(request.UpdatedAt))
        {
            message = "agent_status.updated_at is required.";
            return false;
        }

        message = string.Empty;
        return true;
    }

    public static AgentStatusResponse Update(AgentStatusUpdateRequest request)
    {
        lock (Gate)
        {
            if (_current is not null
                && !string.Equals(_current.SessionId, request.SessionId, StringComparison.Ordinal))
            {
                History.Clear();
            }

            _current = new StoredAgentStatus(
                request.SessionId!.Trim(),
                request.Phase!.Trim(),
                request.Status!.Trim(),
                request.UpdatedAt!.Trim(),
                NormalizeOptional(request.ActionId),
                NormalizeOptional(request.ActionLabel),
                NormalizeOptional(request.Reason),
                NormalizeOptional(request.Detail),
                NormalizeOptional(request.Confidence),
                request.Turn,
                request.Step,
                DateTimeOffset.UtcNow);
            AppendHistory(_current);
            return CreateResponse(_current, DateTimeOffset.UtcNow);
        }
    }

    public static AgentStatusResponse GetCurrent()
    {
        lock (Gate)
        {
            return CreateResponse(_current, DateTimeOffset.UtcNow);
        }
    }

    internal static AgentStatusResponse GetCurrent(DateTimeOffset now)
    {
        lock (Gate)
        {
            return CreateResponse(_current, now);
        }
    }

    public static AgentStatusResponse Clear()
    {
        lock (Gate)
        {
            _current = null;
            History.Clear();
            return EmptyResponse();
        }
    }

    private static AgentStatusResponse CreateResponse(StoredAgentStatus? current, DateTimeOffset now)
    {
        if (current is null)
        {
            return EmptyResponse();
        }

        var stale = now - current.ReceivedAtUtc > StaleTtl;
        return new AgentStatusResponse(
            Empty: false,
            Stale: stale,
            Status: stale ? "stale" : current.Status,
            SourceStatus: current.Status,
            SessionId: current.SessionId,
            Phase: current.Phase,
            ActionId: current.ActionId,
            ActionLabel: current.ActionLabel,
            Reason: current.Reason,
            Detail: current.Detail,
            Confidence: current.Confidence,
            Turn: current.Turn,
            Step: current.Step,
            UpdatedAt: current.UpdatedAt,
            History: BuildHistory(now));
    }

    private static AgentStatusResponse EmptyResponse()
    {
        return new AgentStatusResponse(
            Empty: true,
            Stale: false,
            Status: "idle",
            History: []);
    }

    private static string? NormalizeOptional(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        return value.Trim();
    }

    private static void AppendHistory(StoredAgentStatus current)
    {
        if (History.Count > 0 && IsSameHistoryEntry(History[^1], current))
        {
            History[^1] = current;
            return;
        }

        if (History.Count > 0 && IsSameDecisionEntry(History[^1], current))
        {
            History[^1] = current;
            return;
        }

        History.Add(current);
        if (History.Count > HistoryLimit)
        {
            History.RemoveRange(0, History.Count - HistoryLimit);
        }
    }

    private static bool IsSameHistoryEntry(StoredAgentStatus left, StoredAgentStatus right)
    {
        return string.Equals(left.Status, right.Status, StringComparison.Ordinal)
            && string.Equals(left.Phase, right.Phase, StringComparison.Ordinal)
            && string.Equals(left.ActionLabel, right.ActionLabel, StringComparison.Ordinal)
            && string.Equals(left.Reason, right.Reason, StringComparison.Ordinal)
            && string.Equals(left.Detail, right.Detail, StringComparison.Ordinal)
            && string.Equals(left.Confidence, right.Confidence, StringComparison.Ordinal)
            && left.Turn == right.Turn
            && left.Step == right.Step;
    }

    private static bool IsSameDecisionEntry(StoredAgentStatus left, StoredAgentStatus right)
    {
        return string.Equals(left.Phase, right.Phase, StringComparison.Ordinal)
            && string.Equals(left.ActionLabel, right.ActionLabel, StringComparison.Ordinal)
            && string.Equals(left.Reason, right.Reason, StringComparison.Ordinal)
            && string.Equals(left.Detail, right.Detail, StringComparison.Ordinal)
            && string.Equals(left.Confidence, right.Confidence, StringComparison.Ordinal)
            && left.Turn == right.Turn
            && left.Step == right.Step
            && !string.IsNullOrWhiteSpace(left.ActionLabel)
            && !string.IsNullOrWhiteSpace(right.ActionLabel);
    }

    private static IReadOnlyList<AgentStatusHistoryEntry> BuildHistory(DateTimeOffset now)
    {
        if (History.Count == 0)
        {
            return [];
        }

        var entries = new List<AgentStatusHistoryEntry>(History.Count);
        foreach (var item in History)
        {
            var stale = now - item.ReceivedAtUtc > StaleTtl;
            entries.Add(new AgentStatusHistoryEntry(
                Status: stale ? "stale" : item.Status,
                Phase: item.Phase,
                ActionLabel: item.ActionLabel,
                Reason: item.Reason,
                Detail: item.Detail,
                Confidence: item.Confidence,
                Turn: item.Turn,
                Step: item.Step,
                UpdatedAt: item.UpdatedAt));
        }

        return entries;
    }

    private sealed record StoredAgentStatus(
        string SessionId,
        string Phase,
        string Status,
        string UpdatedAt,
        string? ActionId,
        string? ActionLabel,
        string? Reason,
        string? Detail,
        string? Confidence,
        int? Turn,
        int? Step,
        DateTimeOffset ReceivedAtUtc);
}
