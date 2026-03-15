using System.Reflection;
using Sts2Mod.StateBridge.Configuration;
using Sts2Mod.StateBridge.Contracts;
using Sts2Mod.StateBridge.Core;
using Sts2Mod.StateBridge.Extraction;
using Sts2Mod.StateBridge.Logging;
using Sts2Mod.StateBridge.Providers;
using Xunit;

namespace Sts2Mod.StateBridge.Tests;

public sealed class RewardPhaseDetectionTests
{
    [Fact]
    public void DetectPhase_ReturnsRewardWhenRewardButtonsAreVisible()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker(
            rewardScreen: new FakeRewardScreen(
                isComplete: true,
                visible: true,
                new FakeRewardButton(new FakeReward("Burning Pact")))));
        var runState = new FakeRunState(new[] { new FakeEnemy("enemy-1", true) });

        var phase = InvokeDetectPhase(reader, runNode, runState);

        Assert.Equal(DecisionPhase.Reward, phase);
    }

    [Fact]
    public void DetectPhase_ReturnsRewardWhenCombatIsClearedAndRewardScreenIsConnected()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker(
            rewardScreen: new FakeRewardScreen(isComplete: true, visible: false)));
        var runState = new FakeRunState(Array.Empty<FakeEnemy>());

        var phase = InvokeDetectPhase(reader, runNode, runState);

        Assert.Equal(DecisionPhase.Reward, phase);
    }

    [Fact]
    public void DetectPhase_FallsBackToOverlayRewardScreenInSinglePlayer()
    {
        var reader = CreateReader();
        var rewardScreen = new FakeRewardScreen(
            isComplete: false,
            visible: true,
            new FakeRewardButton(new FakeReward("Battle Trance")));
        var runNode = new FakeRunNode(
            new FakeScreenTracker(),
            new FakeGlobalUi(new FakeOverlayStack(rewardScreen)));
        var runState = new FakeRunState(new[] { new FakeEnemy("enemy-1", true) });

        var phase = InvokeDetectPhase(reader, runNode, runState);

        Assert.Equal(DecisionPhase.Reward, phase);
    }

    [Fact]
    public void BuildCombatWindow_UsesTransitionWindowAndNoActionsWhenEnemiesAreGone()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker());
        var runState = new FakeRunState(Array.Empty<FakeEnemy>());

        var window = InvokeBuildCombatWindow(reader, runNode, runState);
        var exported = new CombatWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));

        Assert.Equal(DecisionPhase.Combat, window.Phase);
        Assert.Empty(window.Actions);
        Assert.Equal("combat_transition", exported.Snapshot.Metadata["window_kind"]);
        Assert.Empty(exported.Actions);
    }

    [Fact]
    public void BuildCombatWindow_SuppressesActionsDuringEnemyTurn()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker());
        var runState = new FakeRunState(
            new[] { new FakeEnemy("enemy-1", true) },
            currentSide: "Enemy",
            hand: new[]
            {
                new FakeCard("Strike")
                {
                    CardId = "strike_red",
                    Description = "Deal {Damage:diff()} [gold]damage[/gold].",
                    RenderedDescription = "Deal 6 damage.",
                    Damage = 6,
                    TargetType = "AnyEnemy",
                    CardType = "Attack",
                    Keywords = new[] { "damage" },
                },
            });

        var window = InvokeBuildCombatWindow(reader, runNode, runState);
        var exported = new CombatWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));

        Assert.Equal(DecisionPhase.Combat, window.Phase);
        Assert.Empty(window.Actions);
        Assert.Equal("Enemy", exported.Snapshot.Metadata["current_side"]);
        Assert.Equal("enemy_turn", exported.Snapshot.Metadata["window_kind"]);
        Assert.Equal(true, exported.Snapshot.Metadata["actions_suppressed"]);
        Assert.Equal("non_player_turn", exported.Snapshot.Metadata["actions_suppressed_reason"]);
        Assert.Empty(exported.Actions);
    }

    [Fact]
    public void BuildCombatWindow_ExportsCombatCardSelectionWindow()
    {
        var reader = CreateReader();
        var selectionScreen = new FakeCombatCardSelectionScreen(
            "消耗1张牌",
            new FakeCardChoice(new FakeCard("Strike") { CardId = "strike_red" }),
            new FakeCardChoice(new FakeCard("Defend") { CardId = "defend_red", TargetType = "Self", CardType = "Skill" }));
        var runNode = new FakeRunNode(
            new FakeScreenTracker(),
            new FakeGlobalUi(new FakeOverlayStack(selectionScreen)));
        var runState = new FakeRunState(new[] { new FakeEnemy("enemy-1", true) });

        var window = InvokeBuildCombatWindow(reader, runNode, runState);
        var exported = new CombatWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));

        Assert.Equal(DecisionPhase.Combat, window.Phase);
        Assert.Equal("combat_card_selection", exported.Snapshot.Metadata["window_kind"]);
        Assert.Equal("exhaust_card", exported.Snapshot.Metadata["selection_kind"]);
        Assert.Equal("消耗1张牌", exported.Snapshot.Metadata["selection_prompt"]);
        Assert.Contains(window.Actions, action => action.Type == "choose_combat_card");
        Assert.Contains(window.Actions, action => action.Type == "cancel_combat_selection");
        Assert.DoesNotContain(window.Actions, action => action.Type == "end_turn");
    }

    [Fact]
    public void BuildCombatWindow_DoesNotExportCancelWhenCombatSelectionCannotCancel()
    {
        var reader = CreateReader();
        var selectionScreen = new FakeCombatCardSelectionScreenNoCancel(
            "消耗1张牌",
            new FakeCardChoice(new FakeCard("Strike") { CardId = "strike_red" }));
        var runNode = new FakeRunNode(
            new FakeScreenTracker(),
            new FakeGlobalUi(new FakeOverlayStack(selectionScreen)));
        var runState = new FakeRunState(new[] { new FakeEnemy("enemy-1", true) });

        var window = InvokeBuildCombatWindow(reader, runNode, runState);
        var exported = new CombatWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));

        Assert.DoesNotContain(window.Actions, action => action.Type == "cancel_combat_selection");
        Assert.Equal(false, exported.Snapshot.Metadata["selection_cancel_available"]);
        Assert.Equal("cancel_hook_not_found", exported.Snapshot.Metadata["selection_cancel_reason"]);
    }

    [Fact]
    public void ExecuteChooseCombatCard_SelectsCurrentChoice()
    {
        var reader = CreateReader();
        var selectionScreen = new FakeCombatCardSelectionScreen(
            "消耗1张牌",
            new FakeCardChoice(new FakeCard("Strike") { CardId = "strike_red" }),
            new FakeCardChoice(new FakeCard("Defend") { CardId = "defend_red", TargetType = "Self", CardType = "Skill" }));
        var runNode = new FakeRunNode(
            new FakeScreenTracker(),
            new FakeGlobalUi(new FakeOverlayStack(selectionScreen)));
        var runState = new FakeRunState(new[] { new FakeEnemy("enemy-1", true) });
        var window = InvokeBuildCombatWindow(reader, runNode, runState);
        var runtimeAction = Assert.Single(window.Actions, candidate =>
            candidate.Type == "choose_combat_card" &&
            Equals(candidate.Parameters["selection_index"], 1));
        var action = new LegalAction(
            "act-select",
            runtimeAction.Type,
            runtimeAction.Label,
            runtimeAction.Parameters,
            runtimeAction.TargetConstraints ?? Array.Empty<string>(),
            runtimeAction.Metadata ?? new Dictionary<string, object?>());
        var request = new ActionRequest("dec-1", "act-select", null, action.Params, Guid.NewGuid().ToString("N"));

        var result = InvokeExecuteChooseCombatCard(reader, runNode, runState, request, action);
        var accepted = (bool)result.GetType().GetProperty("Accepted")!.GetValue(result)!;
        var metadata = (IReadOnlyDictionary<string, object?>)result.GetType().GetProperty("Metadata")!.GetValue(result)!;

        Assert.True(accepted);
        Assert.NotNull(selectionScreen.SelectedChoice);
        Assert.Equal("Defend", selectionScreen.SelectedChoice!.Card.Title);
        Assert.Equal("choose_combat_card", metadata["action_type"]);
        Assert.Equal(1, metadata["selection_index"]);
    }

    [Fact]
    public void ExecuteChooseCombatCard_RejectsWhenSelectionWindowChanges()
    {
        var reader = CreateReader();
        var selectionScreen = new FakeCombatCardSelectionScreen(
            "消耗1张牌",
            new FakeCardChoice(new FakeCard("Strike") { CardId = "strike_red" }),
            new FakeCardChoice(new FakeCard("Defend") { CardId = "defend_red", TargetType = "Self", CardType = "Skill" }));
        var runNode = new FakeRunNode(
            new FakeScreenTracker(),
            new FakeGlobalUi(new FakeOverlayStack(selectionScreen)));
        var runState = new FakeRunState(new[] { new FakeEnemy("enemy-1", true) });
        var action = new LegalAction(
            "act-select",
            "choose_combat_card",
            "Choose Defend",
            new Dictionary<string, object?>
            {
                ["selection_index"] = 1,
                ["card_id"] = "card-mismatched",
                ["card_name"] = "Defend",
            },
            Array.Empty<string>(),
            new Dictionary<string, object?>());
        var request = new ActionRequest("dec-1", "act-select", null, action.Params, Guid.NewGuid().ToString("N"));

        var result = InvokeExecuteChooseCombatCard(reader, runNode, runState, request, action);
        var accepted = (bool)result.GetType().GetProperty("Accepted")!.GetValue(result)!;
        var errorCode = (string?)result.GetType().GetProperty("ErrorCode")!.GetValue(result);

        Assert.False(accepted);
        Assert.Equal("selection_window_changed", errorCode);
    }

    [Fact]
    public void ExtractCardRewardChoiceItems_ReadsPlayerHandHoldersCollections()
    {
        var reader = CreateReader();
        var firstHolder = new FakeNHandCardHolder(new FakeCard("Strike") { CardId = "strike_red" });
        var secondHolder = new FakeNHandCardHolder(new FakeCard("Defend") { CardId = "defend_red", TargetType = "Self", CardType = "Skill" });
        var playerHand = new FakeNPlayerHandSelection(firstHolder, secondHolder);

        var choices = InvokeExtractCardRewardChoiceItems(reader, playerHand);

        Assert.Equal(2, choices.Count);
        Assert.Same(firstHolder, choices[0]);
        Assert.Same(secondHolder, choices[1]);
    }

    [Fact]
    public void TryExecutePlayerHandCombatSelection_SelectsHolderAndConfirms()
    {
        var reader = CreateReader();
        var firstHolder = new FakeNHandCardHolder(new FakeCard("Strike") { CardId = "strike_red" });
        var secondHolder = new FakeNHandCardHolder(new FakeCard("Defend") { CardId = "defend_red", TargetType = "Self", CardType = "Skill" });
        var playerHand = new FakeNPlayerHandSelection(firstHolder, secondHolder);

        var (handled, rawResult) = InvokeTryExecutePlayerHandCombatSelection(reader, playerHand, secondHolder, 1);
        var accepted = (bool)rawResult.GetType().GetProperty("Accepted")!.GetValue(rawResult)!;
        var metadata = (IReadOnlyDictionary<string, object?>)rawResult.GetType().GetProperty("Metadata")!.GetValue(rawResult)!;

        Assert.True(handled);
        Assert.True(accepted);
        Assert.Same(secondHolder, playerHand.LastPressedHolder);
        Assert.True(playerHand.CheckIfSelectionCompleteCalled);
        Assert.True(playerHand.ConfirmPressed);
        Assert.Equal("player_hand_selection.OnHolderPressed", metadata["runtime_handler"]);
    }

    [Fact]
    public void BuildCombatWindow_ExportsRichCardsEnemiesPowersAndRunState()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker());
        var currentPoint = new FakeMapPoint("Monster", new FakeMapCoord(1, 1),
            new FakeMapPoint("Elite", new FakeMapCoord(2, 2)));
        var strengthPotion = new FakePotion("Strength Potion")
        {
            PotionId = "strength_potion",
            Description = "Gain {Strength:diff()} [gold]Strength[/gold] this turn.",
            RenderedDescription = "Gain 2 Strength this turn.",
            Strength = 2,
            HoverTips = new[]
            {
                new FakeHoverTip("strength_potion", "Strength Potion", "Gain {Strength:diff()} [gold]Strength[/gold] this turn."),
                new FakeHoverTip("strength", "Strength", "Increases attack damage."),
            },
        };
        var runState = new FakeRunState(
            new[]
            {
                new FakeEnemy("enemy-1", true, intent: "Attack+Weak", intentDamage: 7, intentHits: 2)
                {
                    CurrentMove = new FakeEnemyMove("Gnaw")
                    {
                        Description = "Deal {Damage:diff()} [gold]damage[/gold]. Gain {Block:diff()} [gold]Block[/gold].",
                        Damage = 7,
                        Block = 4,
                        Keywords = new[] { "damage", "block" },
                        HoverTips = new[]
                        {
                            new FakeHoverTip("damage", "Damage", "Reduces HP."),
                            new FakeHoverTip("block", "Block", "Prevents damage until next turn."),
                        },
                    },
                    Traits = new[] { "beast" },
                    Keywords = new[] { "ambush" },
                },
            },
            currentMapPoint: currentPoint,
            hand: new[]
            {
                new FakeCard("Strike")
                {
                    CardId = "strike_red",
                    Description = "Deal {Damage:diff()} [gold]damage[/gold].",
                    RenderedDescription = "Deal 6 damage.",
                    Damage = 6,
                    TargetType = "AnyEnemy",
                    CardType = "Attack",
                    Rarity = "Starter",
                    Traits = new[] { "starter" },
                    Keywords = new[] { "damage" },
                    HoverTips = new[]
                    {
                        new FakeHoverTip("damage", "Damage", "Reduces HP."),
                    },
                },
            },
            drawPile: new[]
            {
                new FakeCard("Pommel Strike")
                {
                    CardId = "pommel_strike",
                    Description = "Deal {Damage:diff()} [gold]damage[/gold]. Draw 1 card.",
                    RenderedDescription = "Deal 9 damage. Draw 1 card.",
                    Damage = 9,
                    TargetType = "AnyEnemy",
                    CardType = "Attack",
                    Rarity = "Common",
                    Keywords = new[] { "damage", "draw" },
                    HoverTips = new[]
                    {
                        new FakeHoverTip("damage", "Damage", "Reduces HP."),
                        new FakeHoverTip("draw", "Draw", "Add cards from your draw pile to your hand."),
                    },
                },
            },
            discardPile: new[]
            {
                new FakeCard("Defend")
                {
                    CardId = "defend_red",
                    Description = "Gain {Block:diff()} [gold]Block[/gold].",
                    RenderedDescription = "Gain 5 Block.",
                    Block = 5,
                    TargetType = "Self",
                    CardType = "Skill",
                    Rarity = "Starter",
                    Keywords = new[] { "block" },
                    HoverTips = new[]
                    {
                        new FakeHoverTip("block", "Block", "Prevents damage until next turn."),
                    },
                },
            },
            potions: new object[] { strengthPotion },
            maxPotionCount: 2);

        var window = InvokeBuildCombatWindow(reader, runNode, runState);
        var exported = new CombatWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));

        var player = exported.Snapshot.Player;
        Assert.NotNull(player);
        var card = Assert.Single(player.Hand);
        Assert.Equal("strike_red", card.CanonicalCardId);
        Assert.Equal("Deal 6 damage.", card.Description);
        var damageGlossary = Assert.Single(card.Glossary ?? Array.Empty<GlossaryAnchor>(), anchor => anchor.GlossaryId == "damage");
        Assert.Equal("damage", damageGlossary.GlossaryId);
        Assert.Equal("runtime_hover_tip", damageGlossary.Source);
        Assert.Equal("Reduces HP.", damageGlossary.Hint);
        Assert.Equal("AnyEnemy", card.TargetType);
        Assert.Contains("starter", card.Traits ?? Array.Empty<string>());
        var drawPileCard = Assert.Single(player.DrawPileCards ?? Array.Empty<CardView>());
        Assert.Equal("pommel_strike", drawPileCard.CanonicalCardId);
        Assert.Contains(drawPileCard.Glossary ?? Array.Empty<GlossaryAnchor>(), anchor => anchor.GlossaryId == "damage" && anchor.Source == "runtime_hover_tip");
        Assert.Equal(1, player.DrawPile);
        var discardPileCard = Assert.Single(player.DiscardPileCards ?? Array.Empty<CardView>());
        Assert.Equal("defend_red", discardPileCard.CanonicalCardId);
        Assert.Contains(discardPileCard.Glossary ?? Array.Empty<GlossaryAnchor>(), anchor => anchor.GlossaryId == "block" && anchor.Source == "runtime_hover_tip");
        Assert.Equal(1, player.DiscardPile);
        Assert.Empty(player.ExhaustPileCards ?? Array.Empty<CardView>());
        Assert.Equal(0, player.ExhaustPile);
        Assert.Contains("Metallicize", player.Powers?.Select(power => power.Name) ?? Array.Empty<string>());
        var playerPower = Assert.Single(player.Powers ?? Array.Empty<PowerView>());
        Assert.Equal("Gain 3 Block at end of turn.", playerPower.Description);
        Assert.Contains(playerPower.Glossary ?? Array.Empty<GlossaryAnchor>(), anchor => anchor.GlossaryId == "metallicize" && anchor.Source == "model_description");
        Assert.Contains(playerPower.Glossary ?? Array.Empty<GlossaryAnchor>(), anchor => anchor.GlossaryId == "block" && anchor.Source == "runtime_hover_tip");
        var potion = Assert.Single(player.Potions);
        Assert.Equal("Strength Potion", potion.Name);
        Assert.Equal("strength_potion", potion.CanonicalPotionId);
        Assert.Equal("Gain 2 **Strength** this turn.", potion.Description);
        var potionGlossary = Assert.Single(potion.Glossary ?? Array.Empty<GlossaryAnchor>());
        Assert.Equal("strength", potionGlossary.GlossaryId);
        Assert.Equal("runtime_hover_tip", potionGlossary.Source);
        Assert.Equal(2, player.PotionCapacity);
        var usePotionAction = Assert.Single(exported.Actions, action => action.Type == "use_potion");
        Assert.Equal("Strength Potion", usePotionAction.Params["potion"]);
        Assert.Equal(0, usePotionAction.Params["potion_index"]);
        Assert.Equal("strength_potion", usePotionAction.Params["canonical_potion_id"]);
        var potionPreview = Assert.IsAssignableFrom<IReadOnlyDictionary<string, object?>>(usePotionAction.Metadata["potion_preview"]);
        Assert.Equal("strength_potion", potionPreview["canonical_potion_id"]);

        var enemy = Assert.Single(exported.Snapshot.Enemies);
        Assert.Equal("louse", enemy.CanonicalEnemyId);
        Assert.Equal("attack_debuff", enemy.IntentType);
        Assert.Equal(7, enemy.IntentDamage);
        Assert.Equal(2, enemy.IntentHits);
        Assert.Contains("weak", enemy.IntentEffects ?? Array.Empty<string>());
        Assert.Equal("Gnaw", enemy.MoveName);
        Assert.Equal("Deal 7 **damage**. Gain 4 **Block**.", enemy.MoveDescription);
        Assert.Contains(enemy.MoveGlossary ?? Array.Empty<GlossaryAnchor>(), anchor => anchor.GlossaryId == "damage" && anchor.Source == "runtime_hover_tip");
        Assert.Contains(enemy.MoveGlossary ?? Array.Empty<GlossaryAnchor>(), anchor => anchor.GlossaryId == "block" && anchor.Source == "runtime_hover_tip");
        Assert.Contains("beast", enemy.Traits ?? Array.Empty<string>());
        Assert.Contains("damage", enemy.Keywords ?? Array.Empty<string>());
        Assert.Contains("vulnerable", enemy.Keywords ?? Array.Empty<string>());
        Assert.Contains("Vulnerable", enemy.Powers?.Select(power => power.Name) ?? Array.Empty<string>());
        Assert.Contains(enemy.Powers ?? Array.Empty<PowerView>(), power =>
            power.PowerId == "vulnerable" &&
            (power.Glossary ?? Array.Empty<GlossaryAnchor>()).Any(anchor => anchor.GlossaryId == "vulnerable" && anchor.Source == "model_description"));

        var runStateSnapshot = exported.Snapshot.RunState;
        Assert.NotNull(runStateSnapshot);
        Assert.Equal(1, runStateSnapshot.Act);
        Assert.Equal(1, runStateSnapshot.Floor);
        Assert.Equal("FakeCombatRoom", runStateSnapshot.CurrentRoomType);
        Assert.Equal("1,1", runStateSnapshot.Map?.CurrentCoord);
        Assert.Contains("Elite@2,2", runStateSnapshot.Map?.ReachableNodes ?? Array.Empty<string>());

        var pileExport = Assert.IsAssignableFrom<IReadOnlyDictionary<string, object?>>(exported.Snapshot.Metadata["pile_export"]);
        var drawPileExport = Assert.IsAssignableFrom<IReadOnlyDictionary<string, object?>>(pileExport["draw_pile"]);
        Assert.Equal(1, drawPileExport["expected_count"]);
        Assert.Equal(1, drawPileExport["exported_count"]);
        Assert.Equal(false, drawPileExport["degraded"]);
        var discardPileExport = Assert.IsAssignableFrom<IReadOnlyDictionary<string, object?>>(pileExport["discard_pile"]);
        Assert.Equal(1, discardPileExport["expected_count"]);
        Assert.Equal(1, discardPileExport["exported_count"]);
        Assert.Equal(false, discardPileExport["degraded"]);
        var enemyExport = Assert.IsAssignableFrom<IReadOnlyDictionary<string, object?>>(exported.Snapshot.Metadata["enemy_export"]);
        Assert.Equal(false, enemyExport["degraded"]);
    }

    [Fact]
    public void BuildCombatWindow_ExportsPotionObjectWhenDescriptionIsMissing()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker());
        var runState = new FakeRunState(
            new[] { new FakeEnemy("enemy-1", true) },
            potions: new object[]
            {
                new FakePotion("Mystery Potion")
                {
                    PotionId = "mystery_potion",
                },
            },
            maxPotionCount: 3);

        var window = InvokeBuildCombatWindow(reader, runNode, runState);
        var exported = new CombatWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));

        var player = exported.Snapshot.Player;
        Assert.NotNull(player);
        var potion = Assert.Single(player.Potions);
        Assert.Equal("Mystery Potion", potion.Name);
        Assert.Null(potion.Description);
        Assert.Equal("mystery_potion", potion.CanonicalPotionId);
        Assert.Equal(3, player.PotionCapacity);
    }

    [Fact]
    public void BuildCombatWindow_KeepsEnemyBaseStateWhenMoveDescriptionIsMissing()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker());
        var runState = new FakeRunState(
            new[] { new FakeEnemy("enemy-1", true, intent: "Attack", intentDamage: 6) });

        var window = InvokeBuildCombatWindow(reader, runNode, runState);
        var exported = new CombatWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));
        var enemy = Assert.Single(exported.Snapshot.Enemies);

        Assert.Equal("Louse", enemy.Name);
        Assert.Equal("attack_6", enemy.Intent);
        Assert.Equal("attack", enemy.IntentType);
        Assert.Equal(6, enemy.IntentDamage);
        Assert.Null(enemy.MoveName);
        Assert.Null(enemy.MoveDescription);
        Assert.Empty(enemy.MoveGlossary ?? Array.Empty<GlossaryAnchor>());
        var enemyExport = Assert.IsAssignableFrom<IReadOnlyDictionary<string, object?>>(exported.Snapshot.Metadata["enemy_export"]);
        Assert.Equal(true, enemyExport["degraded"]);
        Assert.True((int)enemyExport["entry_count"] >= 1);
    }

    [Fact]
    public void BuildCombatWindow_NormalizesGenericIntentLabelsIntoStableTypeAndSuppressesGenericMoveName()
    {
        var logger = new FakeBridgeLogger();
        var reader = CreateReader(logger);
        var runNode = new FakeRunNode(new FakeScreenTracker());
        var runState = new FakeRunState(
            new[]
            {
                new FakeEnemy("enemy-1", true, intent: "策略", intentDamage: 0, intentType: "策略")
                {
                    CurrentMove = new FakeEnemyMove("策略")
                    {
                        Description = "这个敌人将要对你施加一个负面效果。",
                    },
                },
            });

        var window = InvokeBuildCombatWindow(reader, runNode, runState);
        var exported = new CombatWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));
        var enemy = Assert.Single(exported.Snapshot.Enemies);

        Assert.Equal("debuff", enemy.Intent);
        Assert.Equal("debuff", enemy.IntentType);
        Assert.Contains("debuff", enemy.IntentEffects ?? Array.Empty<string>());
        Assert.Null(enemy.MoveName);
        Assert.Equal("这个敌人将要对你施加一个负面效果。", enemy.MoveDescription);
        var debuffGlossary = Assert.Single(enemy.MoveGlossary ?? Array.Empty<GlossaryAnchor>());
        Assert.Equal("debuff", debuffGlossary.GlossaryId);
        Assert.Equal("fallback_builtin", debuffGlossary.Source);
        Assert.Equal("会削弱目标。", debuffGlossary.Hint);
        Assert.DoesNotContain(logger.WarnMessages, message => message.Contains("Glossary hint missing glossary_id=debuff", StringComparison.Ordinal));
    }

    [Fact]
    public void BuildCombatWindow_DegradesMissingPileWithoutFailingSnapshot()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker());
        var runState = new FakeRunState(
            new[] { new FakeEnemy("enemy-1", true) },
            hand: new[]
            {
                new FakeCard("Strike")
                {
                    CardId = "strike_red",
                    Description = "Deal {Damage:diff()} [gold]damage[/gold].",
                    RenderedDescription = "Deal 6 damage.",
                    Damage = 6,
                    TargetType = "AnyEnemy",
                    CardType = "Attack",
                    Keywords = new[] { "damage" },
                },
            },
            drawPileObject: new FakeBrokenPile(),
            discardPile: new[]
            {
                new FakeCard("Defend")
                {
                    CardId = "defend_red",
                    Description = "Gain {Block:diff()} [gold]Block[/gold].",
                    Block = 5,
                    TargetType = "Self",
                    CardType = "Skill",
                    Keywords = new[] { "block" },
                },
            });

        var window = InvokeBuildCombatWindow(reader, runNode, runState);
        var exported = new CombatWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));
        var player = Assert.IsType<PlayerState>(exported.Snapshot.Player);

        Assert.Empty(player.DrawPileCards ?? Array.Empty<CardView>());
        Assert.Equal(0, player.DrawPile);
        Assert.Single(player.DiscardPileCards ?? Array.Empty<CardView>());

        var pileExport = Assert.IsAssignableFrom<IReadOnlyDictionary<string, object?>>(exported.Snapshot.Metadata["pile_export"]);
        var drawPileExport = Assert.IsAssignableFrom<IReadOnlyDictionary<string, object?>>(pileExport["draw_pile"]);
        Assert.Equal(true, drawPileExport["degraded"]);
        Assert.Equal("cards_collection_missing", drawPileExport["fallback_reason"]);
        Assert.Equal(0, drawPileExport["expected_count"]);
        Assert.Equal(0, drawPileExport["exported_count"]);
    }

    [Fact]
    public void BuildCombatWindow_RendersTemplateFallbackAndGlossaryWithoutRuntimeRenderedText()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker());
        var runState = new FakeRunState(
            new[] { new FakeEnemy("enemy-1", true) },
            hand: new[]
            {
                new FakeCard("Defend")
                {
                    CardId = "defend_red",
                    Description = "Gain {Block:diff()} [gold]Block[/gold].",
                    Block = 5,
                    TargetType = "Self",
                    CardType = "Skill",
                    Keywords = new[] { "block" },
                },
            });

        var window = InvokeBuildCombatWindow(reader, runNode, runState);
        var exported = new CombatWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));
        var player = exported.Snapshot.Player;
        Assert.NotNull(player);
        var card = Assert.Single(player.Hand);

        Assert.Equal("Gain 5 **Block**.", card.Description);
        Assert.Contains(card.Glossary ?? Array.Empty<GlossaryAnchor>(), anchor => anchor.GlossaryId == "block");
    }

    [Fact]
    public void BuildCombatWindow_UsesDynamicVarsWhenDirectDamageMemberIsMissing()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker());
        var runState = new FakeRunState(
            new[] { new FakeEnemy("enemy-1", true) },
            hand: new[]
            {
                new FakeCard("Strike")
                {
                    CardId = "strike_red",
                    Description = "Deal {Damage:diff()} [gold]damage[/gold].",
                    Damage = null,
                    DynamicVars = new FakeDynamicVars(damage: 6),
                    TargetType = "AnyEnemy",
                    CardType = "Attack",
                    Rarity = "Starter",
                    Traits = new[] { "starter" },
                    Keywords = new[] { "damage" },
                },
            });

        var window = InvokeBuildCombatWindow(reader, runNode, runState);
        var exported = new CombatWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));
        var player = exported.Snapshot.Player;
        Assert.NotNull(player);
        var card = Assert.Single(player.Hand);

        Assert.Equal("Deal 6 **damage**.", card.Description);
        Assert.Contains(card.Glossary ?? Array.Empty<GlossaryAnchor>(), anchor => anchor.GlossaryId == "damage");
    }

    [Fact]
    public void BuildCombatWindow_KeepsTemplateFallbackWhenDynamicValueCannotBeResolved()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker());
        var runState = new FakeRunState(
            new[] { new FakeEnemy("enemy-1", true) },
            hand: new[]
            {
                new FakeCard("Battle Trance")
                {
                    CardId = "battle_trance",
                    Description = "Draw {Draw:diff()} cards.",
                    TargetType = "Self",
                    CardType = "Skill",
                    Keywords = new[] { "draw" },
                },
            });

        var window = InvokeBuildCombatWindow(reader, runNode, runState);
        var exported = new CombatWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));
        var player = exported.Snapshot.Player;
        Assert.NotNull(player);
        var card = Assert.Single(player.Hand);

        Assert.Equal("Draw {Draw:diff()} cards.", card.Description);
        Assert.Contains(card.Glossary ?? Array.Empty<GlossaryAnchor>(), anchor => anchor.GlossaryId == "draw");
    }

    [Fact]
    public void BuildRewardWindow_ExportsRewardChoicesAndDiagnostics()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker(
            rewardScreen: new FakeRewardScreen(
                isComplete: false,
                visible: true,
                new FakeRewardButton(new FakeReward("Inflame")),
                new FakeRewardButton(new FakeReward("Pommel Strike")))));
        var runState = new FakeRunState(Array.Empty<FakeEnemy>());

        var window = InvokeBuildRewardWindow(reader, runNode, runState);
        var exported = new RewardWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));

        Assert.Equal(DecisionPhase.Reward, window.Phase);
        Assert.Equal(new[] { "Inflame", "Pommel Strike" }, window.Rewards);
        Assert.Contains(window.Actions, action => action.Type == "choose_reward");
        Assert.Contains(window.Actions, action => action.Type == "skip_reward");
        Assert.Equal(DecisionPhase.Reward, exported.Snapshot.Phase);
        Assert.Equal("reward_choice", exported.Snapshot.Metadata["window_kind"]);
        Assert.True(exported.Snapshot.Metadata.ContainsKey("phase_detection"));
    }

    [Fact]
    public void DetectPhase_ReturnsRewardWhenCardRewardSelectionOverlayIsVisible()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(
            new FakeScreenTracker(),
            new FakeGlobalUi(new FakeOverlayStack(new FakeCardRewardSelectionScreen(
                new FakeCardChoice(new FakeCard("Strike")),
                new FakeCardChoice(new FakeCard("Defend"))))));
        var runState = new FakeRunState(Array.Empty<FakeEnemy>());

        var phase = InvokeDetectPhase(reader, runNode, runState);

        Assert.Equal(DecisionPhase.Reward, phase);
    }

    [Fact]
    public void BuildRewardWindow_ExportsCardRewardSelectionAsRewardWindow()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(
            new FakeScreenTracker(),
            new FakeGlobalUi(new FakeOverlayStack(new FakeCardRewardSelectionScreen(
                new FakeCardChoice(new FakeCard("Strike")),
                new FakeCardChoice(new FakeCard("Defend"))))));
        var runState = new FakeRunState(Array.Empty<FakeEnemy>());

        var window = InvokeBuildRewardWindow(reader, runNode, runState);
        var exported = new RewardWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));

        Assert.Equal(DecisionPhase.Reward, window.Phase);
        Assert.Equal(new[] { "Strike", "Defend" }, window.Rewards);
        Assert.Contains(window.Actions, action => action.Type == "choose_reward");
        Assert.Contains(window.Actions, action => action.Type == "skip_reward");
        Assert.Equal("reward_card_selection", exported.Snapshot.Metadata["window_kind"]);
        Assert.Equal("card_reward_selection", exported.Snapshot.Metadata["reward_subphase"]);
        Assert.True(exported.Snapshot.Metadata.ContainsKey("overlay_top_type"));
    }

    [Fact]
    public void BuildRewardWindow_DoesNotExportSkipRewardWhenCardSelectionCannotSkip()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(
            new FakeScreenTracker(),
            new FakeGlobalUi(new FakeOverlayStack(new FakeCardRewardSelectionScreenNoSkip(
                new FakeCardChoice(new FakeCard("Strike"))))));
        var runState = new FakeRunState(Array.Empty<FakeEnemy>());

        var window = InvokeBuildRewardWindow(reader, runNode, runState);
        var exported = new RewardWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));

        Assert.DoesNotContain(window.Actions, action => action.Type == "skip_reward");
        Assert.Equal(false, exported.Snapshot.Metadata["reward_skip_available"]);
        Assert.Equal("skip_hook_not_found", exported.Snapshot.Metadata["reward_skip_reason"]);
    }

    [Fact]
    public void BuildRewardWindow_ExportsAdvanceActionWhenRewardScreenNeedsContinue()
    {
        var reader = CreateReader();
        var rewardScreen = new FakeRewardScreen(isComplete: true, visible: true, advanceButton: new FakeAdvanceButton("前进"));
        var runNode = new FakeRunNode(new FakeScreenTracker(rewardScreen: rewardScreen));
        var runState = new FakeRunState(Array.Empty<FakeEnemy>());

        var window = InvokeBuildRewardWindow(reader, runNode, runState);
        var exported = new RewardWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));

        Assert.Empty(window.Rewards);
        Assert.Contains(window.Actions, action => action.Type == "advance_reward");
        Assert.Equal("reward_advance", exported.Snapshot.Metadata["window_kind"]);
        Assert.Equal("reward_advance", exported.Snapshot.Metadata["reward_subphase"]);
        Assert.Equal(true, exported.Snapshot.Metadata["reward_advance_available"]);
    }

    [Fact]
    public void ExecuteAdvanceReward_PrefersRewardScreenProceedHandler()
    {
        var reader = CreateReader();
        var button = new FakeAdvanceButton("前进");
        var rewardScreen = new FakeRewardScreen(isComplete: true, visible: true, advanceButton: button);
        var runNode = new FakeRunNode(new FakeScreenTracker(rewardScreen: rewardScreen));
        var action = new LegalAction(
            "act-advance",
            "advance_reward",
            "前进",
            new Dictionary<string, object?> { ["button_label"] = "前进" },
            Array.Empty<string>(),
            new Dictionary<string, object?>());
        var request = new ActionRequest("dec-1", "act-advance", null, action.Params, Guid.NewGuid().ToString("N"));

        var result = InvokeExecuteAdvanceReward(reader, runNode, request, action);
        var accepted = (bool)result.GetType().GetProperty("Accepted")!.GetValue(result)!;
        var metadata = (IReadOnlyDictionary<string, object?>)result.GetType().GetProperty("Metadata")!.GetValue(result)!;

        Assert.True(accepted);
        Assert.True(rewardScreen.ProceedPressed);
        Assert.False(button.Clicked);
        Assert.Equal("advance_reward", metadata["action_type"]);
        Assert.Equal("map", metadata["next_window_expected"]);
        Assert.Equal("reward_screen.OnProceedButtonPressed", metadata["runtime_handler"]);
    }

    [Fact]
    public void BuildRewardWindow_UsesTransitionWindowWhenRewardIsCompleteButAdvanceButtonIsMissing()
    {
        var reader = CreateReader();
        var rewardScreen = new FakeRewardScreen(isComplete: true, visible: true);
        var runNode = new FakeRunNode(new FakeScreenTracker(rewardScreen: rewardScreen));
        var runState = new FakeRunState(Array.Empty<FakeEnemy>());

        var window = InvokeBuildRewardWindow(reader, runNode, runState);
        var exported = new RewardWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));

        Assert.Empty(window.Actions);
        Assert.Equal("reward_transition", exported.Snapshot.Metadata["window_kind"]);
        Assert.Equal("reward_transition", exported.Snapshot.Metadata["reward_subphase"]);
    }

    [Fact]
    public void BuildMapWindow_ExportsReadyMetadataAndChooseMapNodeActions()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker(mapScreenVisible: true));
        var currentPoint = new FakeMapPoint("Current", new FakeMapCoord(0, 0),
            new FakeMapPoint("Monster", new FakeMapCoord(1, 2)),
            new FakeMapPoint("Elite", new FakeMapCoord(2, 2)));
        var runState = new FakeRunState(Array.Empty<FakeEnemy>(), currentRoom: new FakeMapRoom(), currentMapPoint: currentPoint);

        var window = InvokeBuildMapWindow(reader, runNode, runState);
        var exported = new MapWindowExtractor().Export(window, new BridgeSessionState(new BridgeOptions()));

        Assert.Equal(DecisionPhase.Map, window.Phase);
        Assert.Equal(new[] { "Monster@1,2", "Elite@2,2" }, window.MapNodes);
        Assert.Equal("map_ready", exported.Snapshot.Metadata["window_kind"]);
        Assert.Equal(true, exported.Snapshot.Metadata["map_ready"]);
        Assert.Equal("current_map_point", exported.Snapshot.Metadata["map_node_source"]);
        Assert.Contains(window.Actions, action => action.Type == "choose_map_node");
    }

    [Fact]
    public void BuildMapWindow_UsesStartingPointFallbackAndTransitionMetadata()
    {
        var reader = CreateReader();
        var runNode = new FakeRunNode(new FakeScreenTracker(mapScreenVisible: true));
        var startingPoint = new FakeMapPoint("Start", new FakeMapCoord(0, 0),
            new FakeMapPoint("Monster", new FakeMapCoord(3, 1)));
        var runState = new FakeRunState(
            Array.Empty<FakeEnemy>(),
            currentRoom: new FakeMapRoom(),
            currentMapPoint: new FakeMapPoint("Current", new FakeMapCoord(0, 0)),
            map: new FakeMap(startingPoint));

        var fallbackWindow = InvokeBuildMapWindow(reader, runNode, runState);
        var fallbackExported = new MapWindowExtractor().Export(fallbackWindow, new BridgeSessionState(new BridgeOptions()));

        Assert.Equal(new[] { "Monster@3,1" }, fallbackWindow.MapNodes);
        Assert.Equal("starting_map_point_fallback", fallbackExported.Snapshot.Metadata["map_node_source"]);
        Assert.Equal("map_ready", fallbackExported.Snapshot.Metadata["window_kind"]);

        var emptyRunState = new FakeRunState(
            Array.Empty<FakeEnemy>(),
            currentRoom: new FakeMapRoom(),
            currentMapPoint: new FakeMapPoint("Current", new FakeMapCoord(0, 0)),
            map: new FakeMap(new FakeMapPoint("Start", new FakeMapCoord(0, 0))));
        var transitionWindow = InvokeBuildMapWindow(reader, runNode, emptyRunState);
        var transitionExported = new MapWindowExtractor().Export(transitionWindow, new BridgeSessionState(new BridgeOptions()));

        Assert.Empty(transitionWindow.Actions);
        Assert.Equal("map_transition", transitionExported.Snapshot.Metadata["window_kind"]);
        Assert.Equal(true, transitionExported.Snapshot.Metadata["no_reachable_nodes"]);
        Assert.Equal("no_reachable_nodes", transitionExported.Snapshot.Metadata["map_node_source"]);
    }

    private static Sts2RuntimeReflectionReader CreateReader(IBridgeLogger? logger = null)
    {
        return new Sts2RuntimeReflectionReader(new BridgeOptions(), new InstallationProbeResult(true, null, null, null, null), logger);
    }

    private static string InvokeDetectPhase(Sts2RuntimeReflectionReader reader, object runNode, object runState)
    {
        var method = typeof(Sts2RuntimeReflectionReader).GetMethod("DetectPhase", BindingFlags.Instance | BindingFlags.NonPublic)!;
        return (string)method.Invoke(reader, new[] { runNode, runState })!;
    }

    private static RuntimeWindowContext InvokeBuildCombatWindow(Sts2RuntimeReflectionReader reader, object runNode, object runState)
    {
        var method = typeof(Sts2RuntimeReflectionReader).GetMethod("BuildCombatWindow", BindingFlags.Instance | BindingFlags.NonPublic)!;
        return (RuntimeWindowContext)method.Invoke(reader, new[] { runNode, runState })!;
    }

    private static RuntimeWindowContext InvokeBuildRewardWindow(Sts2RuntimeReflectionReader reader, object runNode, object runState)
    {
        var method = typeof(Sts2RuntimeReflectionReader).GetMethod("BuildRewardWindow", BindingFlags.Instance | BindingFlags.NonPublic)!;
        return (RuntimeWindowContext)method.Invoke(reader, new[] { runNode, runState })!;
    }

    private static RuntimeWindowContext InvokeBuildMapWindow(Sts2RuntimeReflectionReader reader, object runNode, object runState)
    {
        var method = typeof(Sts2RuntimeReflectionReader).GetMethod("BuildMapWindow", BindingFlags.Instance | BindingFlags.NonPublic)!;
        return (RuntimeWindowContext)method.Invoke(reader, new[] { runNode, runState })!;
    }

    private static object InvokeExecuteAdvanceReward(Sts2RuntimeReflectionReader reader, object runNode, ActionRequest request, LegalAction action)
    {
        var method = typeof(Sts2RuntimeReflectionReader).GetMethod("ExecuteAdvanceReward", BindingFlags.Instance | BindingFlags.NonPublic)!;
        return method.Invoke(reader, new object[] { runNode, request, action })!;
    }

    private static object InvokeExecuteChooseCombatCard(Sts2RuntimeReflectionReader reader, object runNode, object runState, ActionRequest request, LegalAction action)
    {
        var method = typeof(Sts2RuntimeReflectionReader).GetMethod("ExecuteChooseCombatCard", BindingFlags.Instance | BindingFlags.NonPublic)!;
        return method.Invoke(reader, new[] { runNode, runState, request, action })!;
    }

    private static List<object> InvokeExtractCardRewardChoiceItems(Sts2RuntimeReflectionReader reader, object cardRewardScreen)
    {
        var method = typeof(Sts2RuntimeReflectionReader).GetMethod("ExtractCardRewardChoiceItems", BindingFlags.Instance | BindingFlags.NonPublic)!;
        return (List<object>)method.Invoke(reader, new[] { cardRewardScreen })!;
    }

    private static (bool Handled, object Result) InvokeTryExecutePlayerHandCombatSelection(
        Sts2RuntimeReflectionReader reader,
        object selectionScreen,
        object choice,
        int selectedIndex)
    {
        var method = typeof(Sts2RuntimeReflectionReader).GetMethod("TryExecutePlayerHandCombatSelection", BindingFlags.Instance | BindingFlags.NonPublic)!;
        var args = new object?[] { selectionScreen, choice, selectedIndex, null };
        var handled = (bool)method.Invoke(reader, args)!;
        return (handled, args[3]!);
    }

    private sealed class FakeRunNode(FakeScreenTracker screenStateTracker, FakeGlobalUi? globalUi = null)
    {
        public FakeScreenTracker ScreenStateTracker { get; } = screenStateTracker;
        public FakeGlobalUi GlobalUi { get; } = globalUi ?? new FakeGlobalUi(new FakeOverlayStack(null));
    }

    private sealed class FakeGlobalUi(FakeOverlayStack overlays)
    {
        public FakeOverlayStack Overlays { get; } = overlays;
    }

    private sealed class FakeOverlayStack(object? screen)
    {
        private readonly object? _screen = screen;

        public object? Peek()
        {
            return _screen;
        }
    }

    private sealed class FakeScreenTracker(FakeRewardScreen? rewardScreen = null, bool mapScreenVisible = false, bool rewardScreenVisible = false)
    {
        public FakeRewardScreen? _connectedRewardsScreen = rewardScreen;
        public bool _mapScreenVisible = mapScreenVisible;
        public bool _rewardScreenVisible = rewardScreenVisible;
    }

    private sealed class FakeRewardScreen
    {
        public FakeRewardScreen(bool isComplete, bool visible, params FakeRewardButton[] buttons)
        {
            IsComplete = isComplete;
            Visible = visible;
            _rewardButtons = new List<FakeRewardButton>(buttons);
        }

        public FakeRewardScreen(bool isComplete, bool visible, FakeAdvanceButton advanceButton, params FakeRewardButton[] buttons)
            : this(isComplete, visible, buttons)
        {
            AdvanceButton = advanceButton;
        }

        public bool IsComplete { get; }
        public bool Visible { get; }
        public List<FakeRewardButton> _rewardButtons { get; }
        public FakeAdvanceButton? AdvanceButton { get; }
        public bool ProceedPressed { get; private set; }

        public IEnumerable<object> GetChildren()
        {
            if (AdvanceButton is not null)
            {
                yield return AdvanceButton;
            }
        }

        public void OnProceedButtonPressed(FakeAdvanceButton _)
        {
            ProceedPressed = true;
        }
    }

    private sealed class FakeRewardButton(FakeReward reward)
    {
        public FakeReward Reward { get; } = reward;
    }

    private sealed class FakeReward(string description)
    {
        public string Description { get; } = description;
    }

    private sealed class FakeAdvanceButton(string text)
    {
        public string Text { get; } = text;
        public bool Visible { get; } = true;
        public bool IsEnabled { get; } = true;
        public bool Clicked { get; private set; }

        public void Click()
        {
            Clicked = true;
        }
    }

    private sealed class FakeHoverTip(string id, string title, string description)
    {
        public string Id { get; } = id;
        public string Title { get; } = title;
        public string Description { get; } = description;
    }

    private sealed class FakeCard(string title)
    {
        public string Title { get; } = title;
        public string CardId { get; init; } = title.ToLowerInvariant();
        public string Name => Title;
        public string Description { get; init; } = string.Empty;
        public string? RenderedDescription { get; init; }
        public bool IsUpgraded { get; init; }
        public string TargetType { get; init; } = "AnyEnemy";
        public string CardType { get; init; } = "Attack";
        public string Rarity { get; init; } = "Common";
        public int CanonicalEnergyCost { get; init; } = 1;
        public int CurrentStarCost { get; init; } = 1;
        public int? Damage { get; init; } = 6;
        public int? Block { get; init; } = 5;
        public bool IsPlayable { get; init; } = true;
        public IReadOnlyList<string> Traits { get; init; } = Array.Empty<string>();
        public IReadOnlyList<string> Keywords { get; init; } = Array.Empty<string>();
        public FakeDynamicVars? DynamicVars { get; init; }
        public IReadOnlyList<FakeHoverTip> HoverTips { get; init; } = Array.Empty<FakeHoverTip>();
    }

    private sealed class FakeDynamicVars(int? damage = null, int? block = null, int? cards = null)
    {
        public int? Damage { get; } = damage;
        public int? Block { get; } = block;
        public int? Cards { get; } = cards;
    }

    private sealed class FakeCardChoice(FakeCard card)
    {
        public FakeCard Card { get; } = card;
    }

    private class FakeNCardHolder(FakeCard card)
    {
        public FakeCard CardModel { get; } = card;
    }

    private sealed class FakeNHandCardHolder(FakeCard card) : FakeNCardHolder(card)
    {
    }

    private sealed class FakeSelectModeConfirmButton;

    private sealed class FakeNPlayerHandSelection(params FakeNHandCardHolder[] holders)
    {
        public bool IsInCardSelection { get; set; } = true;
        public bool InSelectMode { get; set; } = true;
        public string SelectionHeader { get; } = "Hand";
        public IReadOnlyList<FakeNHandCardHolder> Holders { get; } = holders;
        public IReadOnlyList<FakeNHandCardHolder> ActiveHolders { get; } = holders;
        public FakeSelectModeConfirmButton _selectModeConfirmButton { get; } = new();
        public FakeNCardHolder? LastPressedHolder { get; private set; }
        public bool CheckIfSelectionCompleteCalled { get; private set; }
        public bool ConfirmPressed { get; private set; }

        public FakeNCardHolder GetCardHolder(FakeCard card)
        {
            return Holders.First(holder => ReferenceEquals(holder.CardModel, card));
        }

        public void OnHolderPressed(FakeNCardHolder holder)
        {
            LastPressedHolder = holder;
        }

        public void SelectCardInSimpleMode(FakeNHandCardHolder holder)
        {
            LastPressedHolder = holder;
        }

        public void CheckIfSelectionComplete()
        {
            CheckIfSelectionCompleteCalled = true;
        }

        public void OnSelectModeConfirmButtonPressed(FakeSelectModeConfirmButton _)
        {
            ConfirmPressed = true;
            InSelectMode = false;
            IsInCardSelection = false;
        }
    }

    private sealed class FakeCardRewardSelectionScreen(params FakeCardChoice[] choices)
    {
        public List<FakeCardChoice> Cards { get; } = new(choices);

        public void SelectCard(FakeCardChoice choice)
        {
        }

        public void Skip()
        {
        }
    }

    private sealed class FakeCardRewardSelectionScreenNoSkip(params FakeCardChoice[] choices)
    {
        public List<FakeCardChoice> Cards { get; } = new(choices);

        public void SelectCard(FakeCardChoice choice)
        {
        }
    }

    private sealed class FakeCombatCardSelectionScreen(string prompt, params FakeCardChoice[] choices)
    {
        public string Prompt { get; } = prompt;
        public List<FakeCardChoice> Cards { get; } = new(choices);
        public FakeCardChoice? SelectedChoice { get; private set; }
        public bool Cancelled { get; private set; }

        public void SelectCard(FakeCardChoice choice)
        {
            SelectedChoice = choice;
        }

        public void Cancel()
        {
            Cancelled = true;
        }
    }

    private sealed class FakeCombatCardSelectionScreenNoCancel(string prompt, params FakeCardChoice[] choices)
    {
        public string Prompt { get; } = prompt;
        public List<FakeCardChoice> Cards { get; } = new(choices);
        public FakeCardChoice? SelectedChoice { get; private set; }

        public void SelectCard(FakeCardChoice choice)
        {
            SelectedChoice = choice;
        }
    }

    private sealed class FakeRunState(
        IEnumerable<FakeEnemy> enemies,
        object? currentRoom = null,
        FakeMapPoint? currentMapPoint = null,
        FakeMap? map = null,
        string currentSide = "Player",
        IReadOnlyList<FakeCard>? hand = null,
        IReadOnlyList<FakeCard>? drawPile = null,
        IReadOnlyList<FakeCard>? discardPile = null,
        IReadOnlyList<FakeCard>? exhaustPile = null,
        IReadOnlyList<object>? potions = null,
        int maxPotionCount = 2,
        object? drawPileObject = null,
        object? discardPileObject = null,
        object? exhaustPileObject = null)
    {
        public object CurrentRoom { get; } = currentRoom ?? new FakeCombatRoom();
        public object CurrentLocation { get; } = "Act1";
        public int ActFloor { get; } = 1;
        public int CurrentActIndex { get; } = 0;
        public int AscensionLevel { get; } = 0;
        public List<FakePlayer> Players { get; } = new()
        {
            new FakePlayer(
                enemies.ToArray(),
                currentSide,
                hand?.ToArray() ?? Array.Empty<FakeCard>(),
                drawPileObject ?? new FakePile(drawPile?.ToArray() ?? Array.Empty<FakeCard>()),
                discardPileObject ?? new FakePile(discardPile?.ToArray() ?? Array.Empty<FakeCard>()),
                exhaustPileObject ?? new FakePile(exhaustPile?.ToArray() ?? Array.Empty<FakeCard>()),
                potions?.ToArray() ?? Array.Empty<object>(),
                maxPotionCount),
        };
        public FakeMapPoint? CurrentMapPoint { get; } = currentMapPoint;
        public FakeMap? Map { get; } = map;
    }

    private sealed class FakeCombatRoom;
    private sealed class FakeMapRoom;

    private sealed class FakeMap(FakeMapPoint startingMapPoint)
    {
        public FakeMapPoint StartingMapPoint { get; } = startingMapPoint;
    }

    private sealed class FakeMapPoint(string pointType, FakeMapCoord coord, params FakeMapPoint[] children)
    {
        public string PointType { get; } = pointType;
        public FakeMapCoord coord { get; } = coord;
        public List<FakeMapPoint> Children { get; } = new(children);
    }

    private sealed class FakeMapCoord(int col, int row)
    {
        public int col { get; } = col;
        public int row { get; } = row;
    }

    private sealed class FakePlayer(
        FakeEnemy[] enemies,
        string currentSide,
        FakeCard[] handCards,
        object drawPile,
        object discardPile,
        object exhaustPile,
        object[] potionSlots,
        int maxPotionCount)
    {
        public int Gold { get; } = 99;
        public int MaxPotionCount { get; } = maxPotionCount;
        public FakeCreature Creature { get; } = new(enemies, currentSide);
        public FakePlayerCombatState PlayerCombatState { get; } = new(handCards, drawPile, discardPile, exhaustPile);
        public List<object> Relics { get; } = new();
        public List<object> PotionSlots { get; } = new(potionSlots);
    }

    private sealed class FakeCreature(FakeEnemy[] enemies, string currentSide)
    {
        public int CurrentHp { get; } = 80;
        public int MaxHp { get; } = 80;
        public int Block { get; } = 0;
        public FakeCombatState CombatState { get; } = new(enemies, currentSide);
        public List<FakePower> Powers { get; } = new()
        {
            new FakePower("metallicize", "Metallicize", 3, "Gain 3 Block at end of turn.")
            {
                HoverTips = new[]
                {
                    new FakeHoverTip("block", "Block", "Prevents damage until next turn."),
                },
            },
        };
    }

    private sealed class FakeCombatState(FakeEnemy[] enemies, string currentSide)
    {
        public int RoundNumber { get; } = 3;
        public string CurrentSide { get; } = currentSide;
        public List<FakeEnemy> Enemies { get; } = new(enemies);
    }

    private sealed class FakeEnemy(string combatId, bool isAlive, string intent = "Attack", int intentDamage = 6, int intentHits = 1, string? intentType = null)
    {
        public string CombatId { get; } = combatId;
        public string Name { get; } = "Louse";
        public string EnemyId { get; } = "louse";
        public int CurrentHp { get; } = isAlive ? 10 : 0;
        public int MaxHp { get; } = 10;
        public int Block { get; } = 0;
        public string Intent { get; } = intent;
        public string? IntentType { get; } = intentType;
        public int IntentDamage { get; } = intentDamage;
        public int IntentHits { get; } = intentHits;
        public bool IsAlive { get; } = isAlive;
        public List<FakePower> Powers { get; } = new() { new FakePower("vulnerable", "Vulnerable", 1, "Vulnerable creatures take 50% more damage from Attacks.") };
        public FakeEnemyMove? CurrentMove { get; init; }
        public IReadOnlyList<string> Traits { get; init; } = Array.Empty<string>();
        public IReadOnlyList<string> Keywords { get; init; } = Array.Empty<string>();
    }

    private sealed class FakeEnemyMove(string name)
    {
        public string Name { get; } = name;
        public string Description { get; init; } = string.Empty;
        public string? RenderedDescription { get; init; }
        public int? Damage { get; init; }
        public int? Block { get; init; }
        public IReadOnlyList<string> Keywords { get; init; } = Array.Empty<string>();
        public IReadOnlyList<FakeHoverTip> HoverTips { get; init; } = Array.Empty<FakeHoverTip>();
    }

    private sealed class FakePlayerCombatState(
        FakeCard[] handCards,
        object drawPile,
        object discardPile,
        object exhaustPile)
    {
        public int Energy { get; } = 3;
        public int Stars { get; } = 0;
        public int MaxEnergy { get; } = 3;
        public FakePile Hand { get; } = new(handCards);
        public object DrawPile { get; } = drawPile;
        public object DiscardPile { get; } = discardPile;
        public object ExhaustPile { get; } = exhaustPile;
    }

    private sealed class FakePile(IEnumerable<object> cards)
    {
        public List<object> Cards { get; } = new(cards);
    }

    private sealed class FakeBrokenPile;

    private sealed class FakePower(string id, string name, int amount, string description)
    {
        public string PowerId { get; } = id;
        public string Name { get; } = name;
        public int Amount { get; } = amount;
        public string Description { get; } = description;
        public string RenderedDescription => description;
        public IReadOnlyList<FakeHoverTip> HoverTips { get; init; } = Array.Empty<FakeHoverTip>();
    }

    private sealed class FakePotion(string title)
    {
        public string Title { get; } = title;
        public string Name => Title;
        public string PotionId { get; init; } = title.ToLowerInvariant().Replace(" ", "_");
        public string? Description { get; init; }
        public string? RenderedDescription { get; init; }
        public int? Strength { get; init; }
        public int? Block { get; init; }
        public IReadOnlyList<FakeHoverTip> HoverTips { get; init; } = Array.Empty<FakeHoverTip>();
    }

    private sealed class FakeBridgeLogger : IBridgeLogger
    {
        public List<string> InfoMessages { get; } = new();
        public List<string> WarnMessages { get; } = new();
        public List<string> ErrorMessages { get; } = new();

        public void Info(string message)
        {
            InfoMessages.Add(message);
        }

        public void Warn(string message)
        {
            WarnMessages.Add(message);
        }

        public void Error(string message, Exception? exception = null)
        {
            ErrorMessages.Add(exception is null ? message : $"{message}: {exception.Message}");
        }
    }
}
