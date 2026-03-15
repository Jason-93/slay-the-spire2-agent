#if STS2_REAL_RUNTIME
using Godot;
using Sts2Mod.StateBridge.Contracts;
using Sts2Mod.StateBridge.Server;
using System.Text;

namespace Sts2Mod.StateBridge.InGame;

internal sealed partial class AgentStatusOverlayNode : Control
{
    public const string NodeNameValue = "Sts2AgentStatusOverlay";

    private ColorRect? _background;
    private Label? _label;
    private string _lastText = string.Empty;

    public AgentStatusOverlayNode()
    {
        Name = NodeNameValue;
        ProcessMode = ProcessModeEnum.Always;
        TopLevel = true;
        ZIndex = 4096;
        ZAsRelative = false;
        MouseFilter = MouseFilterEnum.Ignore;
        Visible = true;
        Position = new Vector2(16.0f, 16.0f);
        Size = new Vector2(620.0f, 220.0f);
        BuildUi();
        Refresh(force: true);
        OverlayDiagnostics.Log("overlay.ctor initialized");
    }

    public override void _EnterTree()
    {
        ProcessMode = ProcessModeEnum.Always;
        SetProcess(true);
        TopLevel = true;
        ZIndex = 4096;
        ZAsRelative = false;
        MouseFilter = MouseFilterEnum.Ignore;
        Visible = true;
        OverlayDiagnostics.Log($"overlay._EnterTree parent={GetParent()?.Name ?? "<none>"}");
    }

    public override void _Ready()
    {
        Name = NodeNameValue;
        ProcessMode = ProcessModeEnum.Always;
        SetProcess(true);
        TopLevel = true;
        ZIndex = 4096;
        ZAsRelative = false;
        MouseFilter = MouseFilterEnum.Ignore;
        Visible = true;
        Position = new Vector2(16.0f, 16.0f);
        Size = new Vector2(620.0f, 220.0f);
        BuildUi();
        OverlayDiagnostics.Log($"overlay._Ready visible={Visible} inside_tree={IsInsideTree()} parent={GetParent()?.Name ?? "<none>"} position={Position} size={Size}");
        OverlayDiagnostics.DumpNodeChain("overlay.ready.chain", this);
        Refresh(force: true);
    }

    public override void _Process(double delta)
    {
        Refresh(force: false);
    }

    public void RefreshFromState(bool force = false)
    {
        BuildUi();
        Refresh(force);
    }

    private void BuildUi()
    {
        if (_label is not null)
        {
            return;
        }

        _background = new ColorRect
        {
            Name = "Background",
            MouseFilter = Control.MouseFilterEnum.Ignore,
            Color = new Color(0.02f, 0.05f, 0.08f, 0.92f),
            Position = Vector2.Zero,
            Size = Size,
            Visible = true,
        };

        _label = new Label
        {
            Name = "Label",
            MouseFilter = Control.MouseFilterEnum.Ignore,
            Visible = true,
            Position = new Vector2(14.0f, 10.0f),
            Size = new Vector2(Size.X - 28.0f, Size.Y - 20.0f),
            AutowrapMode = TextServer.AutowrapMode.WordSmart,
            HorizontalAlignment = HorizontalAlignment.Left,
            VerticalAlignment = VerticalAlignment.Top,
            Text = "STS2 Agent\nstatus: booting",
            ClipText = false,
        };
        _label.AddThemeColorOverride("font_color", new Color(0.98f, 0.98f, 0.95f, 1.0f));
        _label.AddThemeColorOverride("font_outline_color", new Color(0.0f, 0.0f, 0.0f, 0.85f));
        _label.AddThemeConstantOverride("outline_size", 1);
        _label.AddThemeFontSizeOverride("font_size", 20);

        var borderTop = CreateBorder(new Vector2(0.0f, 0.0f), new Vector2(Size.X, 3.0f));
        var borderBottom = CreateBorder(new Vector2(0.0f, Size.Y - 3.0f), new Vector2(Size.X, 3.0f));
        var borderLeft = CreateBorder(new Vector2(0.0f, 0.0f), new Vector2(3.0f, Size.Y));
        var borderRight = CreateBorder(new Vector2(Size.X - 3.0f, 0.0f), new Vector2(3.0f, Size.Y));

        AddChild(_background);
        AddChild(borderTop);
        AddChild(borderBottom);
        AddChild(borderLeft);
        AddChild(borderRight);
        AddChild(_label);
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
        OverlayDiagnostics.Log($"overlay.Refresh force={force} text={text.Replace('\n', ' ')}");
    }

    private static ColorRect CreateBorder(Vector2 position, Vector2 size)
    {
        return new ColorRect
        {
            MouseFilter = Control.MouseFilterEnum.Ignore,
            Color = new Color(0.96f, 0.78f, 0.22f, 1.0f),
            Position = position,
            Size = size,
            Visible = true,
        };
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
            return builder.ToString().TrimEnd();
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

        var reason = Truncate(snapshot.Reason, 240);
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

        return normalized[..Math.Max(0, limit - 1)].TrimEnd() + "...";
    }
}
#endif
