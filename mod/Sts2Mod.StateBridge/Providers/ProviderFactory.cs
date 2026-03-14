using Sts2Mod.StateBridge.Configuration;
using Sts2Mod.StateBridge.Logging;

namespace Sts2Mod.StateBridge.Providers;

public static class ProviderFactory
{
    public static (IGameStateProvider Provider, BridgeOptions EffectiveOptions) Create(BridgeOptions options, IBridgeLogger logger)
    {
        var probe = Sts2InstallationLocator.Discover(options);
        var isInGameRuntime = AppDomain.CurrentDomain.GetAssemblies()
            .Any(assembly => string.Equals(assembly.GetName().Name, "sts2", StringComparison.OrdinalIgnoreCase));
        var effectiveOptions = new BridgeOptions
        {
            Host = options.Host,
            Port = options.Port,
            ProtocolVersion = options.ProtocolVersion,
            ModVersion = options.ModVersion,
            GameVersion = probe.GameVersion ?? options.GameVersion,
            ProviderMode = probe.RuntimeAvailable && options.PreferRuntimeProvider
                ? (isInGameRuntime ? "in-game-runtime" : "runtime-host")
                : options.ProviderMode,
            Sts2ManagedDir = probe.ManagedDir ?? options.Sts2ManagedDir,
            Sts2ModLoaderDir = probe.ModLoaderDir ?? options.Sts2ModLoaderDir,
            PreferRuntimeProvider = options.PreferRuntimeProvider,
            AllowDebugPhaseOverride = options.AllowDebugPhaseOverride,
            ReadOnly = options.ReadOnly,
            LogDescriptionSuccesses = options.LogDescriptionSuccesses,
        };

        foreach (var note in probe.Notes)
        {
            logger.Warn(note);
        }

        if (probe.RuntimeAvailable && options.PreferRuntimeProvider)
        {
            logger.Info($"Using runtime provider with managed dir: {probe.ManagedDir}");
            return (new Sts2RuntimeStateProvider(effectiveOptions, probe, logger), effectiveOptions);
        }

        logger.Info("Using fixture provider");
        return (new FixtureGameStateProvider(effectiveOptions), effectiveOptions);
    }
}
