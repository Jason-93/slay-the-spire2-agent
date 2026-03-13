using Sts2Mod.StateBridge.Configuration;
using Sts2Mod.StateBridge.Logging;

namespace Sts2Mod.StateBridge.Providers;

public static class ProviderFactory
{
    public static (IGameStateProvider Provider, BridgeOptions EffectiveOptions) Create(BridgeOptions options, IBridgeLogger logger)
    {
        var probe = Sts2InstallationLocator.Discover(options);
        var effectiveOptions = new BridgeOptions
        {
            Host = options.Host,
            Port = options.Port,
            ProtocolVersion = options.ProtocolVersion,
            ModVersion = options.ModVersion,
            GameVersion = probe.GameVersion ?? options.GameVersion,
            ProviderMode = probe.RuntimeAvailable && options.PreferRuntimeProvider ? "runtime" : options.ProviderMode,
            Sts2ManagedDir = probe.ManagedDir ?? options.Sts2ManagedDir,
            Sts2ModLoaderDir = probe.ModLoaderDir ?? options.Sts2ModLoaderDir,
            PreferRuntimeProvider = options.PreferRuntimeProvider,
            AllowDebugPhaseOverride = options.AllowDebugPhaseOverride,
            ReadOnly = options.ReadOnly,
        };

        foreach (var note in probe.Notes)
        {
            logger.Warn(note);
        }

        if (probe.RuntimeAvailable && options.PreferRuntimeProvider)
        {
            logger.Info($"Using runtime provider with managed dir: {probe.ManagedDir}");
            return (new Sts2RuntimeStateProvider(effectiveOptions, probe), effectiveOptions);
        }

        logger.Info("Using fixture provider");
        return (new FixtureGameStateProvider(effectiveOptions), effectiveOptions);
    }
}
