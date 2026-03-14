using System.Reflection;
using Sts2Mod.StateBridge.Configuration;
using Sts2Mod.StateBridge.Contracts;
using Sts2Mod.StateBridge.Providers;
using Xunit;

namespace Sts2Mod.StateBridge.Tests;

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

    private sealed class FakeGameInstance(FakeMenuRoot mainMenu)
    {
        public FakeMenuRoot MainMenu { get; } = mainMenu;
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
