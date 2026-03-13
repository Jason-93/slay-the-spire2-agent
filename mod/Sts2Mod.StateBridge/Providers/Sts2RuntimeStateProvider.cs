using Sts2Mod.StateBridge.Configuration;
using Sts2Mod.StateBridge.Contracts;

namespace Sts2Mod.StateBridge.Providers;

public sealed class Sts2RuntimeStateProvider : IGameStateProvider
{
    private readonly BridgeOptions _options;
    private readonly InstallationProbeResult _probe;

    public Sts2RuntimeStateProvider(BridgeOptions options, InstallationProbeResult probe)
    {
        _options = options;
        _probe = probe;
    }

    public HealthResponse GetHealth()
    {
        return new HealthResponse(
            Healthy: false,
            ProtocolVersion: _options.ProtocolVersion,
            ModVersion: _options.ModVersion,
            GameVersion: _options.GameVersion,
            ProviderMode: "runtime",
            ReadOnly: _options.ReadOnly,
            Status: $"runtime provider not implemented yet; managed_dir={_probe.ManagedDir ?? "missing"}");
    }

    public DecisionSnapshot GetSnapshot(string? requestedPhase = null)
    {
        throw new NotSupportedException($"Real STS2 runtime extraction is not wired yet. ManagedDir={_probe.ManagedDir ?? "missing"}");
    }

    public IReadOnlyList<LegalAction> GetActions(string? requestedPhase = null)
    {
        throw new NotSupportedException($"Real STS2 runtime action export is not wired yet. ManagedDir={_probe.ManagedDir ?? "missing"}");
    }
}
