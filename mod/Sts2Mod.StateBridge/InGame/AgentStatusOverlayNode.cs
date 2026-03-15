#if STS2_REAL_RUNTIME
using Godot;
using Sts2Mod.StateBridge.Contracts;
using Sts2Mod.StateBridge.Server;
using System.Text;

namespace Sts2Mod.StateBridge.InGame;

internal sealed partial class AgentStatusOverlayNode : CanvasLayer
{
    public const string NodeNameValue = "Sts2AgentStatusOverlay";

    private RichTextLabel? _label;
    private string _lastText = string.Empty;

    public override void _EnterTree()
    {
        ProcessMode = ProcessModeEnum.Always;
        SetProcess(true);
    }

    public override void _Ready()
    {
        Name = NodeNameValue;
        Layer = 100;
        ProcessMode = ProcessModeEnum.Always;
        SetProcess(true);
        BuildUi();
        Refresh(force: true);
    }

    public override void _Process(double delta)
    {
        Refresh(force: false);
    }

    private void BuildUi()
    {
        if (_label is not null)
        {
            return;
        }

        var panel = new PanelContainer
        {
            Name = "Panel",
            MouseFilter = Control.MouseFilterEnum.Ignore,
        };
        panel.AnchorLeft = 1.0f;
        panel.AnchorRight = 1.0f;
        panel.AnchorTop = 0.0f;
        panel.AnchorBottom = 0.0f;
        panel.OffsetLeft = -500.0f;
        panel.OffsetTop = 16.0f;
        panel.OffsetRight = -16.0f;
        panel.OffsetBottom = 236.0f;

        var panelStyle = new StyleBoxFlat
        {
            BgColor = new Color(0.05f, 0.08f, 0.12f, 0.88f),
            BorderColor = new Color(0.36f, 0.60f, 0.76f, 0.95f),
        };
        panelStyle.SetBorderWidthAll(1);
        panelStyle.SetCornerRadiusAll(6);
        panel.AddThemeStyleboxOverride("panel", panelStyle);

        var margin = new MarginContainer
        {
            MouseFilter = Control.MouseFilterEnum.Ignore,
        };
        margin.AddThemeConstantOverride("margin_left", 12);
        margin.AddThemeConstantOverride("margin_top", 10);
        margin.AddThemeConstantOverride("margin_right", 12);
        margin.AddThemeConstantOverride("margin_bottom", 10);

        _label = new RichTextLabel
        {
            Name = "Label",
            BbcodeEnabled = false,
            FitContent = false,
            ScrollActive = false,
            AutowrapMode = TextServer.AutowrapMode.WordSmart,
            MouseFilter = Control.MouseFilterEnum.Ignore,
            SelectionEnabled = false,
        };
        _label.AddThemeColorOverride("default_color", Colors.White);
        _label.AddThemeColorOverride("font_outline_color", new Color(0.0f, 0.0f, 0.0f, 0.65f));
        _label.AddThemeConstantOverride("outline_size", 1);

        margin.AddChild(_label);
        panel.AddChild(margin);
        AddChild(panel);
    }

    private void Refresh(bool force)
    {
        if (_label is null)
        {
            return;
        }

        var text = BuildOverlayText(AgentStatusStateStore.GetCurrent());
        if (!force && string.Equals(text, _lastText, StringComparison.Ordinal))
        {
            return;
        }

        _label.Text = text;
        _lastText = text;
    }

    private static string BuildOverlayText(AgentStatusResponse snapshot)
    {
        var builder = new StringBuilder();
        builder.AppendLine("STS2 Agent");
        builder.Append("status: ").Append(snapshot.Status);
        if (snapshot.Stale && !string.IsNullOrWhiteSpace(snapshot.SourceStatus))
        {
            builder.Append(" (").Append(snapshot.SourceStatus).Append(')');
        }
        builder.AppendLine();

        if (snapshot.Empty)
        {
            builder.Append("phase: idle");
            return builder.ToString();
        }

        builder.Append("phase: ").Append(snapshot.Phase ?? "unknown").AppendLine();
        builder.Append("action: ").Append(snapshot.ActionLabel ?? snapshot.ActionId ?? "none").AppendLine();

        if (!string.IsNullOrWhiteSpace(snapshot.Confidence))
        {
            builder.Append("confidence: ").Append(snapshot.Confidence).AppendLine();
        }

        if (snapshot.Turn is not null || snapshot.Step is not null)
        {
            builder.Append("turn/step: ")
                .Append(snapshot.Turn?.ToString() ?? "-")
                .Append('/')
                .Append(snapshot.Step?.ToString() ?? "-")
                .AppendLine();
        }

        var reason = Truncate(snapshot.Reason, 220);
        if (!string.IsNullOrWhiteSpace(reason))
        {
            builder.Append("reason: ").Append(reason);
        }

        return builder.ToString().TrimEnd();
    }

    private static string Truncate(string? value, int limit)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        var normalized = value.Replace("\r\n", "\n", StringComparison.Ordinal).Replace('\r', '\n').Trim();
        if (normalized.Length <= limit)
        {
            return normalized;
        }

        return normalized[..Math.Max(0, limit - 1)].TrimEnd() + "…";
    }
}
#endif
