using System.Reflection;
using Sts2Mod.StateBridge.Configuration;
using Sts2Mod.StateBridge.Contracts;
using Sts2Mod.StateBridge.Core;
using Sts2Mod.StateBridge.Extraction;
using Sts2Mod.StateBridge.Providers;
using Xunit;

namespace Sts2Mod.StateBridge.Tests;

public sealed class RuntimeCardIdentityTests
{
    [Fact]
    public void CreateCardId_DifferentiatesDuplicateCardsByHandSlot()
    {
        var first = new FakeCard("打击");
        var second = new FakeCard("打击");

        var firstId = RuntimeCardIdentity.CreateCardId(first, 0);
        var secondId = RuntimeCardIdentity.CreateCardId(second, 1);

        Assert.NotEqual(firstId, secondId);
    }

    [Fact]
    public void Export_AssignsDistinctActionIdsForDuplicateCardNames()
    {
        var extractor = new CombatWindowExtractor();
        var session = new BridgeSessionState(new BridgeOptions());

        var window = new RuntimeWindowContext(
            DecisionPhase.Combat,
            new RuntimePlayerState(
                80,
                80,
                0,
                3,
                99,
                new[]
                {
                    new RuntimeCard("card-a", "打击", 1, true),
                    new RuntimeCard("card-b", "打击", 1, true),
                },
                10,
                0,
                0,
                new[] { "燃烧之血" },
                Array.Empty<string>()),
            new[] { new RuntimeEnemyState("enemy-1", "小啃兽", 10, 10, 0, "unknown", true) },
            Array.Empty<string>(),
            Array.Empty<string>(),
            false,
            new Dictionary<string, object?>
            {
                ["source"] = "sts2_runtime",
                ["window_kind"] = "player_turn",
            },
            new[]
            {
                new RuntimeActionDefinition(
                    "play_card",
                    "Play 打击",
                    new Dictionary<string, object?>
                    {
                        ["card_id"] = "card-a",
                        ["card_name"] = "打击",
                        ["target_type"] = "AnyEnemy",
                    },
                    new[] { "enemy-1" },
                    new Dictionary<string, object?> { ["playable"] = true }),
                new RuntimeActionDefinition(
                    "play_card",
                    "Play 打击",
                    new Dictionary<string, object?>
                    {
                        ["card_id"] = "card-b",
                        ["card_name"] = "打击",
                        ["target_type"] = "AnyEnemy",
                    },
                    new[] { "enemy-1" },
                    new Dictionary<string, object?> { ["playable"] = true }),
            });

        var exported = extractor.Export(window, session);

        Assert.Equal(2, exported.Actions.Count);
        Assert.NotEqual(exported.Actions[0].ActionId, exported.Actions[1].ActionId);
        Assert.NotEqual(exported.Actions[0].Params["card_id"], exported.Actions[1].Params["card_id"]);
    }

    [Fact]
    public void ExecutePlayCard_MatchesExactCardInstanceByCardId()
    {
        var reader = new Sts2RuntimeReflectionReader(new BridgeOptions(), new InstallationProbeResult(true, null, null, null, null));
        var first = new FakeCard("打击");
        var second = new FakeCard("打击");
        var runState = new FakeRunState(first, second);
        var secondCardId = RuntimeCardIdentity.CreateCardId(second, 1);
        var action = new LegalAction(
            "act-2",
            "play_card",
            "Play 打击",
            new Dictionary<string, object?>
            {
                ["card_id"] = secondCardId,
                ["card_name"] = "打击",
            },
            Array.Empty<string>(),
            new Dictionary<string, object?>());
        var request = new ActionRequest("dec-1", action.ActionId, action.Type, new Dictionary<string, object?>());

        var result = InvokeExecutePlayCard(reader, runState, request, action);

        Assert.True(result.Accepted);
        Assert.False(first.WasPlayed);
        Assert.True(second.WasPlayed);
    }

    [Fact]
    public void ExecutePlayCard_RejectsStaleCardId()
    {
        var reader = new Sts2RuntimeReflectionReader(new BridgeOptions(), new InstallationProbeResult(true, null, null, null, null));
        var runState = new FakeRunState(new FakeCard("打击"));
        var action = new LegalAction(
            "act-stale",
            "play_card",
            "Play 打击",
            new Dictionary<string, object?>
            {
                ["card_id"] = "card-missing",
                ["card_name"] = "打击",
            },
            Array.Empty<string>(),
            new Dictionary<string, object?>());
        var request = new ActionRequest("dec-1", action.ActionId, action.Type, new Dictionary<string, object?>());

        var result = InvokeExecutePlayCard(reader, runState, request, action);

        Assert.False(result.Accepted);
        Assert.Equal("stale_action", result.ErrorCode);
    }

    private static dynamic InvokeExecutePlayCard(Sts2RuntimeReflectionReader reader, object runState, ActionRequest request, LegalAction action)
    {
        var method = typeof(Sts2RuntimeReflectionReader).GetMethod("ExecutePlayCard", BindingFlags.Instance | BindingFlags.NonPublic)!;
        return method.Invoke(reader, new object?[] { runState, request, action })!;
    }

    private sealed class FakeRunState(params FakeCard[] cards)
    {
        public List<FakePlayer> Players { get; } = new() { new FakePlayer(cards) };
    }

    private sealed class FakePlayer(params FakeCard[] cards)
    {
        public FakePlayerCombatState PlayerCombatState { get; } = new(cards);
    }

    private sealed class FakePlayerCombatState(params FakeCard[] cards)
    {
        public FakeHand Hand { get; } = new(cards);
    }

    private sealed class FakeHand(params FakeCard[] cards)
    {
        public List<FakeCard> Cards { get; } = new(cards);
    }

    private sealed class FakeCard(string title)
    {
        public string Title { get; } = title;

        public string Name => title;

        public bool IsPlayable => true;

        public bool WasPlayed { get; private set; }

        public bool TryManualPlay(object? target)
        {
            WasPlayed = true;
            return true;
        }
    }
}
