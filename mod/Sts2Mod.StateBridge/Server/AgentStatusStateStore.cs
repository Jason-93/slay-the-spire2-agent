using Sts2Mod.StateBridge.Contracts;

namespace Sts2Mod.StateBridge.Server;

internal static class AgentStatusStateStore
{
    private static readonly object Gate = new();
    private static readonly TimeSpan StaleTtl = TimeSpan.FromSeconds(5);
    private static StoredAgentStatus? _current;

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

    public static AgentStatusResponse Clear()
    {
        lock (Gate)
        {
            _current = null;
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
            UpdatedAt: current.UpdatedAt);
    }

    private static AgentStatusResponse EmptyResponse()
    {
        return new AgentStatusResponse(
            Empty: true,
            Stale: false,
            Status: "idle");
    }

    private static string? NormalizeOptional(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        return value.Trim();
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
