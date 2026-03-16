using Sts2Mod.StateBridge.Configuration;
using Sts2Mod.StateBridge.Contracts;
using Sts2Mod.StateBridge.Core;
using Sts2Mod.StateBridge.Extraction;

namespace Sts2Mod.StateBridge.Providers;

public sealed class FixtureGameStateProvider : IGameStateProvider
{
    private readonly BridgeOptions _options;
    private readonly BridgeSessionState _sessionState;
    private readonly Dictionary<string, RuntimeWindowContext> _windows;
    private readonly Dictionary<string, RuntimeWindowContext> _rewardWindows;
    private readonly Dictionary<string, RuntimeWindowContext> _eventWindows;
    private readonly Dictionary<string, RuntimeWindowContext> _menuWindows;
    private readonly Dictionary<string, IWindowExtractor> _extractors;
    private string _currentPhase = DecisionPhase.Combat;
    private int _rewardStage;
    private int _eventStage;
    private int _menuStage;

    public FixtureGameStateProvider(BridgeOptions options)
    {
        _options = options;
        _sessionState = new BridgeSessionState(options);
        _extractors = new IWindowExtractor[]
        {
            new CombatWindowExtractor(),
            new RewardWindowExtractor(),
            new MapWindowExtractor(),
            new EventWindowExtractor(),
            new MenuWindowExtractor(),
            new TerminalWindowExtractor(),
        }.ToDictionary(extractor => extractor.Phase, StringComparer.OrdinalIgnoreCase);
        _windows = CreateWindows();
        _rewardWindows = CreateRewardWindows();
        _eventWindows = CreateEventWindows();
        _menuWindows = CreateMenuWindows();
    }

    public HealthResponse GetHealth()
    {
        return new HealthResponse(
            Healthy: true,
            ProtocolVersion: _options.ProtocolVersion,
            ModVersion: _options.ModVersion,
            GameVersion: _options.GameVersion,
            ProviderMode: _options.ProviderMode,
            ReadOnly: _options.ReadOnly,
            Status: "ok");
    }

    public DecisionSnapshot GetSnapshot(string? requestedPhase = null)
    {
        return Export(requestedPhase).Snapshot;
    }

    public IReadOnlyList<LegalAction> GetActions(string? requestedPhase = null)
    {
        return Export(requestedPhase).Actions;
    }

    public ActionResponse ApplyAction(ActionRequest request)
    {
        if (_options.ReadOnly)
        {
            return Reject(request, "read_only", "Bridge is running in read-only mode.");
        }

        var exported = Export(null);
        if (!string.Equals(request.DecisionId, exported.Snapshot.DecisionId, StringComparison.Ordinal))
        {
            return Reject(request, "stale_decision", "Requested decision_id is no longer current.");
        }

        var action = ResolveAction(exported.Actions, request);
        if (action is null)
        {
            return Reject(request, "illegal_action", "Requested action is not part of the current legal action set.");
        }

        switch (action.Type)
        {
            case "continue_run":
                _menuStage = 0;
                _rewardStage = 0;
                _currentPhase = DecisionPhase.Map;
                break;
            case "start_new_run":
                _menuStage = 1;
                _rewardStage = 0;
                _currentPhase = DecisionPhase.Menu;
                break;
            case "select_character":
                _menuStage = 1;
                _currentPhase = DecisionPhase.Menu;
                break;
            case "confirm_start_run":
                _menuStage = 0;
                _currentPhase = DecisionPhase.Map;
                break;
            case "play_card":
            case "use_potion":
            case "end_turn":
                _currentPhase = DecisionPhase.Reward;
                _rewardStage = 0;
                break;
            case "choose_event_option":
                _eventStage = _eventStage == 0 ? 1 : 2;
                _currentPhase = DecisionPhase.Event;
                break;
            case "continue_event":
                _eventStage = 0;
                _currentPhase = DecisionPhase.Map;
                break;
            case "choose_reward":
                if (string.Equals(_currentPhase, DecisionPhase.Reward, StringComparison.OrdinalIgnoreCase) && _rewardStage == 0)
                {
                    // Simulate selecting "Add a card" reward which opens the card reward selection screen.
                    _rewardStage = 1;
                    _currentPhase = DecisionPhase.Reward;
                    break;
                }

                _rewardStage = 0;
                _currentPhase = DecisionPhase.Map;
                break;
            case "skip_reward":
            case "skip":
                _rewardStage = 0;
                _currentPhase = DecisionPhase.Map;
                break;
            case "choose_map_node":
                _currentPhase = DecisionPhase.Combat;
                break;
            default:
                return Reject(request, "unsupported_action", $"Fixture provider cannot execute action type '{action.Type}'.");
        }

        var nextSnapshot = Export(null).Snapshot;
        var metadata = new Dictionary<string, object?>
        {
            ["next_decision_id"] = nextSnapshot.DecisionId,
            ["next_phase"] = nextSnapshot.Phase,
        };
        if (string.Equals(action.Type, "use_potion", StringComparison.Ordinal))
        {
            metadata["action_type"] = "use_potion";
            metadata["potion_index"] = action.Params.TryGetValue("potion_index", out var potionIndex) ? potionIndex : null;
            metadata["runtime_handler"] = "fixture.use_potion";
        }

        return Accept(request, action, "Fixture action applied.", metadata);
    }

    private ExportedWindow Export(string? requestedPhase)
    {
        var phase = ResolvePhase(requestedPhase);
        _currentPhase = phase;
        var context = phase switch
        {
            var value when string.Equals(value, DecisionPhase.Reward, StringComparison.OrdinalIgnoreCase)
                => _rewardStage == 0 ? _rewardWindows["reward_choice"] : _rewardWindows["reward_card_selection"],
            var value when string.Equals(value, DecisionPhase.Event, StringComparison.OrdinalIgnoreCase)
                => _eventStage switch
                {
                    0 => _eventWindows["event_choice"],
                    1 => _eventWindows["event_card_selection"],
                    _ => _eventWindows["event_continue"],
                },
            var value when string.Equals(value, DecisionPhase.Menu, StringComparison.OrdinalIgnoreCase)
                => _menuStage == 0 ? _menuWindows["main_menu"] : _menuWindows["new_run_setup"],
            _ => _windows[phase],
        };
        return _extractors[phase].Export(context, _sessionState);
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

    private static ActionResponse Reject(ActionRequest request, string errorCode, string message)
    {
        return new ActionResponse(
            RequestId: request.RequestId ?? Guid.NewGuid().ToString("N"),
            DecisionId: request.DecisionId,
            ActionId: request.ActionId,
            Status: "rejected",
            ErrorCode: errorCode,
            Message: message,
            Metadata: new Dictionary<string, object?>());
    }

    private static ActionResponse Accept(ActionRequest request, LegalAction action, string message, IReadOnlyDictionary<string, object?> metadata)
    {
        return new ActionResponse(
            RequestId: request.RequestId ?? Guid.NewGuid().ToString("N"),
            DecisionId: request.DecisionId,
            ActionId: action.ActionId,
            Status: "accepted",
            ErrorCode: null,
            Message: message,
            Metadata: metadata);
    }

    private string ResolvePhase(string? requestedPhase)
    {
        if (!_options.AllowDebugPhaseOverride || string.IsNullOrWhiteSpace(requestedPhase))
        {
            return _currentPhase;
        }

        if (_windows.ContainsKey(requestedPhase))
        {
            return requestedPhase;
        }

        return requestedPhase.ToLowerInvariant() switch
        {
            "combat" => DecisionPhase.Combat,
            "reward" => DecisionPhase.Reward,
            "map" => DecisionPhase.Map,
            "event" => DecisionPhase.Event,
            "menu" => DecisionPhase.Menu,
            "terminal" => DecisionPhase.Terminal,
            _ => _currentPhase,
        };
    }

    private static Dictionary<string, RuntimeWindowContext> CreateWindows()
    {
        var drawPileCards = CreateFixtureDrawPileCards();
        var discardPileCards = CreateFixtureDiscardPileCards();
        return new Dictionary<string, RuntimeWindowContext>(StringComparer.OrdinalIgnoreCase)
        {
            [DecisionPhase.Combat] = new RuntimeWindowContext(
                DecisionPhase.Combat,
                new RuntimePlayerState(
                    Hp: 70,
                    MaxHp: 80,
                    Block: 6,
                    Energy: 3,
                    Gold: 99,
                    Hand: new[]
                    {
                        new RuntimeCard(
                            "strike_red#0",
                            "Strike",
                            1,
                            Playable: true,
                            InstanceCardId: "strike_red#0",
                            CanonicalCardId: "strike_red",
                            Description: "Deal 6 **damage**.",
                            CostForTurn: 1,
                            Upgraded: false,
                            TargetType: "AnyEnemy",
                            CardType: "Attack",
                            Rarity: "Starter",
                            Traits: new[] { "starter" },
                            Keywords: new[] { "damage" },
                            Glossary: new[] { new GlossaryAnchor("damage", "Damage", "Reduces HP.", "runtime_hover_tip") }),
                        new RuntimeCard(
                            "defend_red#1",
                            "Defend",
                            1,
                            Playable: true,
                            InstanceCardId: "defend_red#1",
                            CanonicalCardId: "defend_red",
                            Description: "Gain 5 **Block**.",
                            CostForTurn: 1,
                            Upgraded: false,
                            TargetType: "Self",
                            CardType: "Skill",
                            Rarity: "Starter",
                            Traits: new[] { "starter" },
                            Keywords: new[] { "block" },
                            Glossary: new[] { new GlossaryAnchor("block", "Block", "Prevents damage until next turn.", "runtime_hover_tip") }),
                        new RuntimeCard(
                            "battle_trance#2",
                            "Battle Trance",
                            0,
                            Playable: true,
                            InstanceCardId: "battle_trance#2",
                            CanonicalCardId: "battle_trance",
                            Description: "Draw {Draw:diff()} cards.",
                            CostForTurn: 0,
                            Upgraded: false,
                            TargetType: "Self",
                            CardType: "Skill",
                            Rarity: "Common",
                            Traits: new[] { "draw" },
                            Keywords: new[] { "draw" },
                            Glossary: new[] { new GlossaryAnchor("draw", "Draw", "Add cards from your draw pile to your hand.", "runtime_hover_tip") }),
                    },
                    DrawPile: 2,
                    DiscardPile: 4,
                    ExhaustPile: 0,
                    Relics: new[]
                    {
                        CreateFixtureRelic(
                            "Burning Blood",
                            "At the end of combat, heal 6 HP.",
                            "burning_blood"),
                    },
                    Potions: new[]
                    {
                        CreateFixturePotion(
                            "Strength Potion",
                            "Gain 2 **Strength** this turn.",
                            "strength_potion",
                            "strength"),
                    },
                    PotionCapacity: 2,
                    Powers: new[]
                    {
                        new RuntimePowerState(
                            "metallicize",
                            "Metallicize",
                            3,
                            "At the end of your turn, gain 3 **Block**.",
                            "metallicize",
                            Glossary: new[]
                            {
                                new GlossaryAnchor("metallicize", "Metallicize", "Gain Block at end of turn.", "model_description"),
                                new GlossaryAnchor("block", "Block", "Prevents damage until next turn.", "runtime_hover_tip"),
                            }),
                    },
                    DrawPileCards: drawPileCards,
                    DiscardPileCards: discardPileCards,
                    ExhaustPileCards: Array.Empty<RuntimeCard>()),
                new[]
                {
                    new RuntimeEnemyState(
                        "jaw_worm_1",
                        "Jaw Worm",
                        38,
                        42,
                        0,
                        "attack_11",
                        IsAlive: true,
                        InstanceEnemyId: "jaw_worm_1",
                        CanonicalEnemyId: "jaw_worm",
                        IntentRaw: "Attack",
                        IntentType: "attack",
                        IntentDamage: 11,
                        IntentHits: 1,
                        IntentBlock: null,
                        IntentEffects: Array.Empty<string>(),
                        Powers: new[]
                        {
                            new RuntimePowerState(
                                "strength",
                                "Strength",
                                3,
                                "Increases attack damage.",
                                "strength",
                                Glossary: new[] { new GlossaryAnchor("damage", "Damage", "Reduces HP.", "runtime_hover_tip") }),
                        },
                        MoveName: "Chomp",
                        MoveDescription: "Deal 11 **damage**.",
                        MoveGlossary: new[]
                        {
                            new GlossaryAnchor("damage", "Damage", "Reduces HP.", "runtime_hover_tip"),
                        },
                        Traits: new[] { "beast" },
                        Keywords: new[] { "damage", "strength", "beast" }),
                },
                Array.Empty<string>(),
                Array.Empty<string>(),
                Terminal: false,
                Metadata: new Dictionary<string, object?>
                {
                    ["room_type"] = "combat",
                    ["turn"] = 1,
                    ["enemy_export"] = new Dictionary<string, object?>
                    {
                        ["enemy_count"] = 1,
                        ["degraded"] = false,
                        ["entry_count"] = 0,
                        ["entries"] = Array.Empty<object>(),
                    },
                },
                Actions: new[]
                {
                    new RuntimeActionDefinition("play_card", "Play Strike", new Dictionary<string, object?> { ["card_id"] = "strike_red#0" }, new[] { "jaw_worm_1" }),
                    new RuntimeActionDefinition("play_card", "Play Defend", new Dictionary<string, object?> { ["card_id"] = "defend_red#1" }),
                    new RuntimeActionDefinition(
                        "use_potion",
                        "Use Strength Potion",
                        new Dictionary<string, object?>
                        {
                            ["potion"] = "Strength Potion",
                            ["potion_index"] = 0,
                            ["canonical_potion_id"] = "strength_potion",
                        },
                        Metadata: new Dictionary<string, object?>
                        {
                            ["potion_preview"] = BuildPotionPreview(
                                CreateFixturePotion(
                                    "Strength Potion",
                                    "Gain 2 **Strength** this turn.",
                                    "strength_potion",
                                    "strength")),
                        }),
                    new RuntimeActionDefinition("end_turn", "End Turn", new Dictionary<string, object?>()),
                },
                RunState: new RuntimeRunState(
                    Act: 1,
                    Floor: 1,
                    CurrentRoomType: "CombatRoom",
                    CurrentLocationType: "Act1",
                    CurrentActIndex: 0,
                    AscensionLevel: 0,
                    Map: new RuntimeRunMapState(
                        CurrentCoord: "0,0",
                        CurrentNodeType: "monster",
                        ReachableNodes: new[] { "monster_left@0,1", "elite_center@1,1", "question_right@2,1" },
                        Source: "fixture"))),
            [DecisionPhase.Map] = new RuntimeWindowContext(
                DecisionPhase.Map,
                new RuntimePlayerState(
                    70,
                    80,
                    0,
                    0,
                    116,
                    Array.Empty<RuntimeCard>(),
                    2,
                    4,
                    0,
                    new[]
                    {
                        CreateFixtureRelic(
                            "Burning Blood",
                            "At the end of combat, heal 6 HP.",
                            "burning_blood"),
                    },
                    Array.Empty<RuntimePotionState>(),
                    2,
                    new[]
                    {
                        new RuntimePowerState(
                            "metallicize",
                            "Metallicize",
                            3,
                            "At the end of your turn, gain 3 **Block**.",
                            "metallicize",
                            Glossary: new[] { new GlossaryAnchor("block", "Block", "Prevents damage until next turn.", "runtime_hover_tip") }),
                    },
                    DrawPileCards: drawPileCards,
                    DiscardPileCards: discardPileCards,
                    ExhaustPileCards: Array.Empty<RuntimeCard>()),
                Array.Empty<RuntimeEnemyState>(),
                Array.Empty<string>(),
                new[] { "monster_left", "elite_center", "question_right" },
                Terminal: false,
                Metadata: new Dictionary<string, object?> { ["room_type"] = "map", ["floor"] = 2 },
                Actions: new[]
                {
                    new RuntimeActionDefinition("choose_map_node", "Choose monster_left", new Dictionary<string, object?> { ["node"] = "monster_left" }),
                    new RuntimeActionDefinition("choose_map_node", "Choose elite_center", new Dictionary<string, object?> { ["node"] = "elite_center" }),
                    new RuntimeActionDefinition("choose_map_node", "Choose question_right", new Dictionary<string, object?> { ["node"] = "question_right" }),
                },
                RunState: new RuntimeRunState(
                    Act: 1,
                    Floor: 2,
                    CurrentRoomType: "MapRoom",
                    CurrentLocationType: "Act1",
                    CurrentActIndex: 0,
                    AscensionLevel: 0,
                    Map: new RuntimeRunMapState(
                        CurrentCoord: "0,1",
                        CurrentNodeType: "monster",
                        ReachableNodes: new[] { "monster_left", "elite_center", "question_right" },
                        Source: "fixture"))),
            [DecisionPhase.Terminal] = new RuntimeWindowContext(
                DecisionPhase.Terminal,
                new RuntimePlayerState(
                    63,
                    80,
                    0,
                    0,
                    116,
                    Array.Empty<RuntimeCard>(),
                    0,
                    0,
                    0,
                    new[]
                    {
                        CreateFixtureRelic(
                            "Burning Blood",
                            "At the end of combat, heal 6 HP.",
                            "burning_blood"),
                    },
                    Array.Empty<RuntimePotionState>(),
                    2,
                    DrawPileCards: Array.Empty<RuntimeCard>(),
                    DiscardPileCards: Array.Empty<RuntimeCard>(),
                    ExhaustPileCards: Array.Empty<RuntimeCard>()),
                Array.Empty<RuntimeEnemyState>(),
                Array.Empty<string>(),
                Array.Empty<string>(),
                Terminal: true,
                Metadata: new Dictionary<string, object?> { ["room_type"] = "victory", ["result"] = "win" },
                Actions: Array.Empty<RuntimeActionDefinition>(),
                RunState: new RuntimeRunState(
                    Act: 1,
                    Floor: 3,
                    CurrentRoomType: "VictoryRoom",
                    CurrentLocationType: "Act1",
                    CurrentActIndex: 0,
                    AscensionLevel: 0,
                    Map: new RuntimeRunMapState(CurrentCoord: "1,2", CurrentNodeType: "boss", ReachableNodes: Array.Empty<string>(), Source: "fixture")))
        };
    }

    private static Dictionary<string, RuntimeWindowContext> CreateMenuWindows()
    {
        return new Dictionary<string, RuntimeWindowContext>(StringComparer.OrdinalIgnoreCase)
        {
            ["main_menu"] = new RuntimeWindowContext(
                DecisionPhase.Menu,
                Player: null,
                Enemies: Array.Empty<RuntimeEnemyState>(),
                Rewards: Array.Empty<string>(),
                MapNodes: Array.Empty<string>(),
                Terminal: false,
                Metadata: new Dictionary<string, object?>
                {
                    ["room_type"] = "menu",
                    ["window_kind"] = "main_menu",
                    ["menu_detection_source"] = "fixture",
                },
                Actions: new[]
                {
                    new RuntimeActionDefinition("continue_run", "Continue", new Dictionary<string, object?> { ["button_label"] = "Continue" }),
                    new RuntimeActionDefinition("start_new_run", "New Run", new Dictionary<string, object?> { ["button_label"] = "New Run" }),
                }),
            ["new_run_setup"] = new RuntimeWindowContext(
                DecisionPhase.Menu,
                Player: null,
                Enemies: Array.Empty<RuntimeEnemyState>(),
                Rewards: Array.Empty<string>(),
                MapNodes: Array.Empty<string>(),
                Terminal: false,
                Metadata: new Dictionary<string, object?>
                {
                    ["room_type"] = "menu",
                    ["window_kind"] = "new_run_setup",
                    ["menu_detection_source"] = "fixture",
                },
                Actions: new[]
                {
                    new RuntimeActionDefinition(
                        "select_character",
                        "Select Ironclad",
                        new Dictionary<string, object?> { ["character_id"] = "ironclad", ["character_label"] = "Ironclad" }),
                    new RuntimeActionDefinition(
                        "select_character",
                        "Select Silent",
                        new Dictionary<string, object?> { ["character_id"] = "silent", ["character_label"] = "Silent" }),
                    new RuntimeActionDefinition(
                        "confirm_start_run",
                        "Start",
                        new Dictionary<string, object?> { ["button_label"] = "Start" }),
                }),
        };
    }

    private static Dictionary<string, RuntimeWindowContext> CreateRewardWindows()
    {
        var drawPileCards = CreateFixtureDrawPileCards();
        var discardPileCards = CreateFixtureDiscardPileCards();
        var player = new RuntimePlayerState(
            70,
            80,
            0,
            0,
            116,
            Array.Empty<RuntimeCard>(),
            2,
            4,
            0,
            new[]
            {
                CreateFixtureRelic(
                    "Burning Blood",
                    "At the end of combat, heal 6 HP.",
                    "burning_blood"),
            },
            Array.Empty<RuntimePotionState>(),
            2,
            new[]
            {
                new RuntimePowerState(
                    "metallicize",
                    "Metallicize",
                    3,
                    "At the end of your turn, gain 3 **Block**.",
                    "metallicize",
                    Glossary: new[] { new GlossaryAnchor("block", "Block", "Prevents damage until next turn.", "runtime_hover_tip") }),
            },
            DrawPileCards: drawPileCards,
            DiscardPileCards: discardPileCards,
            ExhaustPileCards: Array.Empty<RuntimeCard>());

        var rewardChoiceLabels = new[]
        {
            "Add a card to your deck.",
            "Gain gold.",
        };

        var rewardChoiceActions = rewardChoiceLabels
            .Select((label, index) => new RuntimeActionDefinition(
                "choose_reward",
                $"Choose {label}",
                new Dictionary<string, object?> { ["reward"] = label, ["reward_index"] = index }))
            .Concat(new[]
            {
                new RuntimeActionDefinition("skip_reward", "Skip Reward", new Dictionary<string, object?>()),
            })
            .ToArray();

        var cardChoiceLabels = new[]
        {
            "Strike",
            "Defend",
            "Bash",
        };

        var cardChoiceActions = cardChoiceLabels
            .Select((label, index) => new RuntimeActionDefinition(
                "choose_reward",
                $"Choose {label}",
                new Dictionary<string, object?> { ["reward"] = label, ["reward_index"] = index }))
            .Concat(new[]
            {
                new RuntimeActionDefinition("skip_reward", "Skip Reward", new Dictionary<string, object?>()),
            })
            .ToArray();

        return new Dictionary<string, RuntimeWindowContext>(StringComparer.OrdinalIgnoreCase)
        {
            ["reward_choice"] = new RuntimeWindowContext(
                DecisionPhase.Reward,
                player,
                Array.Empty<RuntimeEnemyState>(),
                rewardChoiceLabels,
                Array.Empty<string>(),
                Terminal: false,
                Metadata: new Dictionary<string, object?>
                {
                    ["room_type"] = "reward",
                    ["window_kind"] = "reward_choice",
                    ["reward_subphase"] = "reward_choice",
                    ["reward_skip_available"] = true,
                },
                Actions: rewardChoiceActions,
                RunState: new RuntimeRunState(
                    Act: 1,
                    Floor: 1,
                    CurrentRoomType: "RewardRoom",
                    CurrentLocationType: "Act1",
                    CurrentActIndex: 0,
                    AscensionLevel: 0,
                    Map: new RuntimeRunMapState(
                        CurrentCoord: "0,0",
                        CurrentNodeType: "monster",
                        ReachableNodes: new[] { "monster_left", "elite_center", "question_right" },
                        Source: "fixture"))),
            ["reward_card_selection"] = new RuntimeWindowContext(
                DecisionPhase.Reward,
                player,
                Array.Empty<RuntimeEnemyState>(),
                cardChoiceLabels,
                Array.Empty<string>(),
                Terminal: false,
                Metadata: new Dictionary<string, object?>
                {
                    ["room_type"] = "reward",
                    ["window_kind"] = "reward_card_selection",
                    ["reward_subphase"] = "card_reward_selection",
                    ["reward_skip_available"] = true,
                },
                Actions: cardChoiceActions,
                RunState: new RuntimeRunState(
                    Act: 1,
                    Floor: 1,
                    CurrentRoomType: "RewardRoom",
                    CurrentLocationType: "Act1",
                    CurrentActIndex: 0,
                    AscensionLevel: 0,
                    Map: new RuntimeRunMapState(
                        CurrentCoord: "0,0",
                        CurrentNodeType: "monster",
                        ReachableNodes: new[] { "monster_left", "elite_center", "question_right" },
                        Source: "fixture"))),
        };
    }

    private static Dictionary<string, RuntimeWindowContext> CreateEventWindows()
    {
        var player = new RuntimePlayerState(
            Hp: 68,
            MaxHp: 80,
            Block: 0,
            Energy: 3,
            Gold: 107,
            Hand: Array.Empty<RuntimeCard>(),
            DrawPile: 12,
            DiscardPile: 2,
            ExhaustPile: 0,
            Relics: new[]
            {
                new RuntimeRelicState("Burning Blood", "At the end of combat, heal 6 HP.", "relic_burning_blood"),
            },
            Potions: Array.Empty<RuntimePotionState>(),
            PotionCapacity: 2,
            Powers: Array.Empty<RuntimePowerState>());

        var eventOptions = new[]
        {
            new Dictionary<string, object?>
            {
                ["option_index"] = 0,
                ["label"] = "献祭：失去6点生命，获得150金币。",
                ["available"] = true,
                ["disabled"] = false,
                ["is_continue"] = false,
            },
            new Dictionary<string, object?>
            {
                ["option_index"] = 1,
                ["label"] = "离开：什么都不做。",
                ["available"] = true,
                ["disabled"] = false,
                ["is_continue"] = false,
            },
        };
        var eventCardOptions = new[]
        {
            new Dictionary<string, object?>
            {
                ["option_index"] = 0,
                ["label"] = "打击",
                ["available"] = true,
                ["disabled"] = false,
                ["is_continue"] = false,
                ["card_id"] = "event-card-0",
                ["preview_text"] = "造成6点**伤害**。",
            },
            new Dictionary<string, object?>
            {
                ["option_index"] = 1,
                ["label"] = "双重打击",
                ["available"] = true,
                ["disabled"] = false,
                ["is_continue"] = false,
                ["card_id"] = "event-card-1",
                ["preview_text"] = "造成5点**伤害**两次。",
            },
        };

        return new Dictionary<string, RuntimeWindowContext>(StringComparer.OrdinalIgnoreCase)
        {
            ["event_choice"] = new RuntimeWindowContext(
                DecisionPhase.Event,
                player,
                Array.Empty<RuntimeEnemyState>(),
                Array.Empty<string>(),
                Array.Empty<string>(),
                Terminal: false,
                Metadata: new Dictionary<string, object?>
                {
                    ["room_type"] = "event",
                    ["window_kind"] = "event_choice",
                    ["event_title"] = "神秘神龛",
                    ["event_body"] = "你在废墟中发现一座古老神龛，似乎在呼唤你献上些许代价。",
                    ["event_options"] = eventOptions,
                    ["event_option_count"] = eventOptions.Length,
                    ["event_continue_available"] = false,
                    ["event_detection_source"] = "fixture.event_choice",
                },
                Actions: new[]
                {
                    new RuntimeActionDefinition(
                        "choose_event_option",
                        "选择 献祭：失去6点生命，获得150金币。",
                        new Dictionary<string, object?>
                        {
                            ["option_index"] = 0,
                            ["option_label"] = "献祭：失去6点生命，获得150金币。",
                        }),
                    new RuntimeActionDefinition(
                        "choose_event_option",
                        "选择 离开：什么都不做。",
                        new Dictionary<string, object?>
                        {
                            ["option_index"] = 1,
                            ["option_label"] = "离开：什么都不做。",
                        }),
                },
                RunState: new RuntimeRunState(
                    Act: 1,
                    Floor: 2,
                    CurrentRoomType: "EventRoom",
                    CurrentLocationType: "Act1",
                    CurrentActIndex: 0,
                    AscensionLevel: 0,
                    Map: new RuntimeRunMapState(
                        CurrentCoord: "1,0",
                        CurrentNodeType: "event",
                        ReachableNodes: new[] { "monster_left", "event_center", "shop_right" },
                        Source: "fixture"))),
            ["event_continue"] = new RuntimeWindowContext(
                DecisionPhase.Event,
                player,
                Array.Empty<RuntimeEnemyState>(),
                Array.Empty<string>(),
                Array.Empty<string>(),
                Terminal: false,
                Metadata: new Dictionary<string, object?>
                {
                    ["room_type"] = "event",
                    ["window_kind"] = "event_continue",
                    ["event_title"] = "神秘神龛",
                    ["event_body"] = "神龛接受了你的决定，空气重新恢复平静。",
                    ["event_options"] = Array.Empty<object>(),
                    ["event_option_count"] = 0,
                    ["event_continue_available"] = true,
                    ["event_continue_label"] = "继续",
                    ["event_detection_source"] = "fixture.event_continue",
                },
                Actions: new[]
                {
                    new RuntimeActionDefinition(
                        "continue_event",
                        "继续",
                        new Dictionary<string, object?>
                        {
                            ["button_label"] = "继续",
                        }),
                },
                RunState: new RuntimeRunState(
                    Act: 1,
                    Floor: 2,
                    CurrentRoomType: "EventRoom",
                    CurrentLocationType: "Act1",
                    CurrentActIndex: 0,
                    AscensionLevel: 0,
                    Map: new RuntimeRunMapState(
                        CurrentCoord: "1,0",
                        CurrentNodeType: "event",
                        ReachableNodes: new[] { "monster_left", "event_center", "shop_right" },
                        Source: "fixture"))),
            ["event_card_selection"] = new RuntimeWindowContext(
                DecisionPhase.Event,
                player,
                Array.Empty<RuntimeEnemyState>(),
                Array.Empty<string>(),
                Array.Empty<string>(),
                Terminal: false,
                Metadata: new Dictionary<string, object?>
                {
                    ["room_type"] = "event",
                    ["window_kind"] = "event_choice",
                    ["event_subphase"] = "card_selection",
                    ["event_title"] = "神秘神龛",
                    ["event_body"] = "选择一张攻击牌附魔。附魔后，它在本场战斗中造成额外伤害。",
                    ["event_selection_prompt"] = "选择一张攻击牌附魔。",
                    ["event_options"] = eventCardOptions,
                    ["event_option_count"] = eventCardOptions.Length,
                    ["event_continue_available"] = false,
                    ["event_detection_source"] = "fixture.event_card_selection",
                },
                Actions: new[]
                {
                    new RuntimeActionDefinition(
                        "choose_event_option",
                        "选择 打击",
                        new Dictionary<string, object?>
                        {
                            ["option_index"] = 0,
                            ["option_label"] = "打击",
                            ["card_id"] = "event-card-0",
                        }),
                    new RuntimeActionDefinition(
                        "choose_event_option",
                        "选择 双重打击",
                        new Dictionary<string, object?>
                        {
                            ["option_index"] = 1,
                            ["option_label"] = "双重打击",
                            ["card_id"] = "event-card-1",
                        }),
                },
                RunState: new RuntimeRunState(
                    Act: 1,
                    Floor: 2,
                    CurrentRoomType: "EventRoom",
                    CurrentLocationType: "Act1",
                    CurrentActIndex: 0,
                    AscensionLevel: 0,
                    Map: new RuntimeRunMapState(
                        CurrentCoord: "1,0",
                        CurrentNodeType: "event",
                        ReachableNodes: new[] { "monster_left", "event_center", "shop_right" },
                        Source: "fixture"))),
        };
    }

    private static RuntimeCard[] CreateFixtureDrawPileCards()
    {
        return new[]
        {
            CreateFixtureCard(
                "card-draw-0",
                "pommel_strike",
                "Pommel Strike",
                1,
                "Deal 9 **damage**. Draw 1 card.",
                targetType: "AnyEnemy",
                cardType: "Attack",
                rarity: "Common",
                traits: new[] { "draw" },
                keywords: new[] { "damage", "draw" }),
            CreateFixtureCard(
                "card-draw-1",
                "bash",
                "Bash",
                2,
                "Deal 8 **damage**. Apply 2 Vulnerable.",
                targetType: "AnyEnemy",
                cardType: "Attack",
                rarity: "Starter",
                traits: new[] { "starter" },
                keywords: new[] { "damage", "vulnerable" }),
        };
    }

    private static RuntimeCard[] CreateFixtureDiscardPileCards()
    {
        return new[]
        {
            CreateFixtureCard(
                "card-discard-0",
                "strike_red",
                "Strike",
                1,
                "Deal 6 **damage**.",
                targetType: "AnyEnemy",
                cardType: "Attack",
                rarity: "Starter",
                traits: new[] { "starter" },
                keywords: new[] { "damage" }),
            CreateFixtureCard(
                "card-discard-1",
                "defend_red",
                "Defend",
                1,
                "Gain 5 **Block**.",
                targetType: "Self",
                cardType: "Skill",
                rarity: "Starter",
                traits: new[] { "starter" },
                keywords: new[] { "block" }),
            CreateFixtureCard(
                "card-discard-2",
                "anger",
                "Anger",
                0,
                "Deal 6 **damage**. Shuffle a copy into your discard pile.",
                targetType: "AnyEnemy",
                cardType: "Attack",
                rarity: "Common",
                keywords: new[] { "damage" }),
            CreateFixtureCard(
                "card-discard-3",
                "flex",
                "Flex",
                0,
                "Gain 2 **Strength** this turn.",
                targetType: "Self",
                cardType: "Skill",
                rarity: "Common",
                keywords: new[] { "strength" }),
        };
    }

    private static RuntimeCard CreateFixtureCard(
        string instanceCardId,
        string canonicalCardId,
        string name,
        int cost,
        string description,
        string targetType,
        string cardType,
        string rarity,
        IReadOnlyList<string>? traits = null,
        IReadOnlyList<string>? keywords = null)
    {
        return new RuntimeCard(
            CardId: instanceCardId,
            Name: name,
            Cost: cost,
            Playable: false,
            InstanceCardId: instanceCardId,
            CanonicalCardId: canonicalCardId,
            Description: description,
            CostForTurn: cost,
            Upgraded: false,
            TargetType: targetType,
            CardType: cardType,
            Rarity: rarity,
            Traits: traits ?? Array.Empty<string>(),
            Keywords: keywords ?? Array.Empty<string>(),
            Glossary: CreateFixtureGlossary(keywords));
    }

    private static RuntimePotionState CreateFixturePotion(
        string name,
        string description,
        string canonicalPotionId,
        params string[] keywords)
    {
        return new RuntimePotionState(
            Name: name,
            Description: description,
            CanonicalPotionId: canonicalPotionId,
            Glossary: CreateFixtureGlossary(keywords));
    }

    private static RuntimeRelicState CreateFixtureRelic(
        string name,
        string description,
        string canonicalRelicId,
        params string[] keywords)
    {
        return new RuntimeRelicState(
            Name: name,
            Description: description,
            CanonicalRelicId: canonicalRelicId,
            Glossary: CreateFixtureGlossary(keywords));
    }

    private static IReadOnlyDictionary<string, object?> BuildPotionPreview(RuntimePotionState potion)
    {
        var preview = new Dictionary<string, object?>
        {
            ["name"] = potion.Name,
            ["description"] = potion.Description,
            ["canonical_potion_id"] = potion.CanonicalPotionId,
            ["glossary"] = potion.Glossary,
        };
        return preview
            .Where(pair => pair.Value is not null)
            .ToDictionary(pair => pair.Key, pair => pair.Value);
    }

    private static IReadOnlyList<GlossaryAnchor> CreateFixtureGlossary(IReadOnlyList<string>? keywords)
    {
        if (keywords is null || keywords.Count == 0)
        {
            return Array.Empty<GlossaryAnchor>();
        }

        var glossary = new List<GlossaryAnchor>();
        foreach (var keyword in keywords)
        {
            switch (keyword)
            {
                case "damage":
                    glossary.Add(new GlossaryAnchor("damage", "Damage", "Reduces HP.", "runtime_hover_tip"));
                    break;
                case "block":
                    glossary.Add(new GlossaryAnchor("block", "Block", "Prevents damage until next turn.", "runtime_hover_tip"));
                    break;
                case "draw":
                    glossary.Add(new GlossaryAnchor("draw", "Draw", "Add cards from your draw pile to your hand.", "runtime_hover_tip"));
                    break;
                case "vulnerable":
                    glossary.Add(new GlossaryAnchor("vulnerable", "Vulnerable", "Vulnerable creatures take 50% more damage from Attacks.", "runtime_hover_tip"));
                    break;
                case "strength":
                    glossary.Add(new GlossaryAnchor("strength", "Strength", "Increases attack damage.", "runtime_hover_tip"));
                    break;
            }
        }

        return glossary;
    }
}
