using System;
using System.Collections.Generic;
using System.Reflection;
using Sts2Mod.StateBridge.Configuration;
using Sts2Mod.StateBridge.Contracts;
using Sts2Mod.StateBridge.Providers;
using Xunit;

namespace Sts2Mod.StateBridge.Tests
{
    public sealed class MenuPhaseBridgeTests
    {
        [Fact]
        public void BuildMenuWindow_ExportsContinueAndNewRunActions()
        {
            var reader = CreateReader();
            var game = new FakeGameInstance(new FakeMenuRoot(
                new FakeButton("Continue"),
                new FakeButton("New Run")));

            var window = InvokeBuildMenuWindow(reader, game);

            Assert.Equal(DecisionPhase.Menu, window.Phase);
            Assert.Equal("main_menu", window.Metadata["window_kind"]);
            Assert.Contains(window.Actions, action => action.Type == "continue_run");
            Assert.Contains(window.Actions, action => action.Type == "start_new_run");
        }

        [Fact]
        public void BuildMenuWindow_SuppressesDangerButtons()
        {
            var reader = CreateReader();
            var game = new FakeGameInstance(new FakeMenuRoot(
                new FakeButton("Exit"),
                new FakeButton("Quit")));

            var window = InvokeBuildMenuWindow(reader, game);

            Assert.Equal(DecisionPhase.Menu, window.Phase);
            Assert.Empty(window.Actions);
            Assert.Equal(true, window.Metadata["menu_action_suppressed"]);
        }

        [Fact]
        public void BuildMenuWindow_ExportsCharacterSelectionWhenDetected()
        {
            var reader = CreateReader();
            var game = new FakeGameInstance(new FakeMenuRoot(
                new FakeButton("Ironclad"),
                new FakeButton("Start")));

            var window = InvokeBuildMenuWindow(reader, game);

            Assert.Equal(DecisionPhase.Menu, window.Phase);
            Assert.Equal("new_run_setup", window.Metadata["window_kind"]);
            Assert.Contains(window.Actions, action => action.Type == "select_character");
            Assert.Contains(window.Actions, action => action.Type == "confirm_start_run");
        }

        [Fact]
        public void ExecuteMenuAction_ClicksResolvedButton()
        {
            var reader = CreateReader();
            var continueButton = new FakeButton("Continue");
            var game = new FakeGameInstance(new FakeMenuRoot(continueButton));

            var action = new LegalAction(
                ActionId: "action-1",
                Type: "continue_run",
                Label: "Continue",
                Params: new Dictionary<string, object?> { ["button_label"] = "Continue" },
                TargetConstraints: Array.Empty<string>(),
                Metadata: new Dictionary<string, object?>());
            var request = new ActionRequest(
                DecisionId: "decision-1",
                ActionId: "action-1",
                ActionType: null,
                Params: new Dictionary<string, object?>(),
                RequestId: "req-1");

            var result = InvokeExecuteMenuAction(reader, game, request, action, "continue_run");

            Assert.True(GetBoolProperty(result, "Accepted"));
            Assert.True(continueButton.Clicked);
        }

        [Fact]
        public void ExecuteMenuAction_PrefersMainMenuContinueHandler()
        {
            var reader = CreateReader();
            var mainMenu = new MegaCrit.Sts2.Core.Nodes.Screens.MainMenu.NMainMenu();
            var continueButton = new MegaCrit.Sts2.Core.Nodes.Screens.MainMenu.NMainMenuContinueButton("ContinueButton", mainMenu);
            mainMenu.SetChildren(continueButton);
            var game = new FakeGameInstance(mainMenu);

            var action = new LegalAction(
                ActionId: "action-continue",
                Type: "continue_run",
                Label: "ContinueButton",
                Params: new Dictionary<string, object?> { ["button_label"] = "ContinueButton" },
                TargetConstraints: Array.Empty<string>(),
                Metadata: new Dictionary<string, object?>());
            var request = new ActionRequest(
                DecisionId: "decision-continue",
                ActionId: "action-continue",
                ActionType: null,
                Params: new Dictionary<string, object?>(),
                RequestId: "req-continue");

            var result = InvokeExecuteMenuAction(reader, game, request, action, "continue_run");

            Assert.True(GetBoolProperty(result, "Accepted"));
            Assert.True(mainMenu.ContinuePressed);
            Assert.False(continueButton.Clicked);
        }

        [Fact]
        public void ExecuteMenuAction_UsesCharacterSelectScreenHandlers()
        {
            var reader = CreateReader();
            var screen = new MegaCrit.Sts2.Core.Nodes.Screens.CharacterSelect.NCharacterSelectScreen();
            var embarkButton = new MegaCrit.Sts2.Core.Nodes.CommonUi.NConfirmButton("ConfirmButton");
            var button = new MegaCrit.Sts2.Core.Nodes.Screens.CharacterSelect.NCharacterSelectButton(
                "IRONCLAD_button",
                new MegaCrit.Sts2.Core.Models.CharacterModel("ironclad"),
                screen);
            screen.Attach(button, embarkButton);
            var game = new FakeGameInstance(screen);

            var selectAction = new LegalAction(
                ActionId: "action-select",
                Type: "select_character",
                Label: "IRONCLAD_button",
                Params: new Dictionary<string, object?>
                {
                    ["button_label"] = "IRONCLAD_button",
                    ["character_id"] = "ironclad",
                },
                TargetConstraints: Array.Empty<string>(),
                Metadata: new Dictionary<string, object?>());
            var confirmAction = new LegalAction(
                ActionId: "action-confirm",
                Type: "confirm_start_run",
                Label: "ConfirmButton",
                Params: new Dictionary<string, object?> { ["button_label"] = "ConfirmButton" },
                TargetConstraints: Array.Empty<string>(),
                Metadata: new Dictionary<string, object?>());
            var request = new ActionRequest(
                DecisionId: "decision-character",
                ActionId: "action-select",
                ActionType: null,
                Params: new Dictionary<string, object?>(),
                RequestId: "req-character");

            var selectResult = InvokeExecuteMenuAction(reader, game, request, selectAction, "select_character");
            var confirmResult = InvokeExecuteMenuAction(reader, game, request, confirmAction, "confirm_start_run");

            Assert.True(GetBoolProperty(selectResult, "Accepted"));
            Assert.True(screen.SelectCharacterCalled);
            Assert.True(GetBoolProperty(confirmResult, "Accepted"));
            Assert.True(screen.EmbarkPressed);
        }

        private static Sts2RuntimeReflectionReader CreateReader()
        {
            return new Sts2RuntimeReflectionReader(new BridgeOptions(), new InstallationProbeResult(true, null, null, null, null));
        }

        private static RuntimeWindowContext InvokeBuildMenuWindow(Sts2RuntimeReflectionReader reader, object gameInstance)
        {
            var method = typeof(Sts2RuntimeReflectionReader).GetMethod("BuildMenuWindow", BindingFlags.Instance | BindingFlags.NonPublic)!;
            return (RuntimeWindowContext)method.Invoke(reader, new[] { gameInstance })!;
        }

        private static object InvokeExecuteMenuAction(Sts2RuntimeReflectionReader reader, object gameInstance, ActionRequest request, LegalAction action, string expectedKind)
        {
            var method = typeof(Sts2RuntimeReflectionReader).GetMethod("ExecuteMenuAction", BindingFlags.Instance | BindingFlags.NonPublic)!;
            return method.Invoke(reader, new object[] { gameInstance, request, action, expectedKind })!;
        }

        private static bool GetBoolProperty(object value, string name)
        {
            var property = value.GetType().GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            Assert.NotNull(property);
            return (bool)(property!.GetValue(value) ?? false);
        }

        private sealed class FakeGameInstance(object mainMenu)
        {
            public object MainMenu { get; } = mainMenu;
        }

        private sealed class FakeMenuRoot(params object[] children)
        {
            private readonly object[] _children = children;

            public object[] GetChildren()
            {
                return _children;
            }
        }

        private sealed class FakeButton(string text)
        {
            public string Text { get; } = text;

            public bool Clicked { get; private set; }

            public object[] GetChildren()
            {
                return Array.Empty<object>();
            }

            public void Click()
            {
                Clicked = true;
            }
        }
    }
}

namespace MegaCrit.Sts2.Core.Nodes.GodotExtensions
{
    internal class NButton
    {
        public bool Visible { get; set; } = true;
    }
}

namespace MegaCrit.Sts2.Core.Models
{
    internal sealed class CharacterModel(string id)
    {
        public string Id { get; } = id;

        public override string ToString()
        {
            return Id;
        }
    }
}

namespace MegaCrit.Sts2.Core.Nodes.CommonUi
{
    internal sealed class NConfirmButton(string name) : MegaCrit.Sts2.Core.Nodes.GodotExtensions.NButton
    {
        public string Name { get; } = name;

        public bool IsEnabled { get; set; } = true;

        public object[] GetChildren()
        {
            return Array.Empty<object>();
        }
    }
}

namespace MegaCrit.Sts2.Core.Nodes.Screens.MainMenu
{
    internal sealed class NMainMenu
    {
        private object[] _children = Array.Empty<object>();

        public bool ContinuePressed { get; private set; }

        public bool SingleplayerOpened { get; private set; }

        public void SetChildren(params object[] children)
        {
            _children = children;
        }

        public object[] GetChildren()
        {
            return _children;
        }

        private void OnContinueButtonPressed(MegaCrit.Sts2.Core.Nodes.GodotExtensions.NButton _)
        {
            ContinuePressed = true;
        }

        public NSingleplayerSubmenu OpenSingleplayerSubmenu()
        {
            SingleplayerOpened = true;
            return new NSingleplayerSubmenu();
        }
    }

    internal sealed class NMainMenuContinueButton(string name, NMainMenu mainMenu) : MegaCrit.Sts2.Core.Nodes.GodotExtensions.NButton
    {
        public string Name { get; } = name;

        public NMainMenu _mainMenu = mainMenu;

        public bool Clicked { get; private set; }

        public object[] GetChildren()
        {
            return Array.Empty<object>();
        }

        public void Click()
        {
            Clicked = true;
        }
    }

    internal sealed class NSingleplayerSubmenu(MegaCrit.Sts2.Core.Nodes.GodotExtensions.NButton? standardButton = null)
    {
        public MegaCrit.Sts2.Core.Nodes.GodotExtensions.NButton _standardButton = standardButton ?? new MegaCrit.Sts2.Core.Nodes.GodotExtensions.NButton();

        public bool OpenCharacterSelectCalled { get; private set; }

        public object[] GetChildren()
        {
            return new object[] { _standardButton };
        }

        private void OpenCharacterSelect(MegaCrit.Sts2.Core.Nodes.GodotExtensions.NButton _)
        {
            OpenCharacterSelectCalled = true;
        }
    }
}

namespace MegaCrit.Sts2.Core.Nodes.Screens.CharacterSelect
{
    internal interface ICharacterSelectButtonDelegate
    {
        void SelectCharacter(NCharacterSelectButton charSelectButton, MegaCrit.Sts2.Core.Models.CharacterModel characterModel);
    }

    internal sealed class NCharacterSelectScreen : ICharacterSelectButtonDelegate
    {
        private readonly List<object> _children = new();

        public NCharacterSelectButton? _selectedButton;

        public MegaCrit.Sts2.Core.Nodes.CommonUi.NConfirmButton? _embarkButton;

        public bool SelectCharacterCalled { get; private set; }

        public bool EmbarkPressed { get; private set; }

        public void Attach(NCharacterSelectButton button, MegaCrit.Sts2.Core.Nodes.CommonUi.NConfirmButton embarkButton)
        {
            _selectedButton = button;
            _embarkButton = embarkButton;
            _children.Clear();
            _children.Add(button);
            _children.Add(embarkButton);
        }

        public object[] GetChildren()
        {
            return _children.ToArray();
        }

        public void SelectCharacter(NCharacterSelectButton charSelectButton, MegaCrit.Sts2.Core.Models.CharacterModel characterModel)
        {
            SelectCharacterCalled = true;
            _selectedButton = charSelectButton;
        }

        private void OnEmbarkPressed(MegaCrit.Sts2.Core.Nodes.GodotExtensions.NButton _)
        {
            EmbarkPressed = true;
        }
    }

    internal sealed class NCharacterSelectButton(string name, MegaCrit.Sts2.Core.Models.CharacterModel character, ICharacterSelectButtonDelegate buttonDelegate) : MegaCrit.Sts2.Core.Nodes.GodotExtensions.NButton
    {
        public string Name { get; } = name;

        public MegaCrit.Sts2.Core.Models.CharacterModel Character { get; } = character;

        public MegaCrit.Sts2.Core.Models.CharacterModel _character = character;

        public ICharacterSelectButtonDelegate _delegate = buttonDelegate;

        public bool IsEnabled { get; set; } = true;

        public bool IsLocked { get; set; }

        public bool Selected { get; private set; }

        public object[] GetChildren()
        {
            return Array.Empty<object>();
        }

        public void Select()
        {
            Selected = true;
        }
    }
}
