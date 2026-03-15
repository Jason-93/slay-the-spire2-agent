#if STS2_REAL_RUNTIME
using Godot;
using Sts2Mod.StateBridge.Contracts;
using Sts2Mod.StateBridge.Server;
using System.Text;

namespace Sts2Mod.StateBridge.InGame;

internal sealed partial class AgentStatusOverlayNode : Control
{
    public const string NodeNameValue = "Sts2AgentStatusOverlay";

    private const float PanelWidth = 348.0f;
    private const float PanelHeight = 124.0f;
    private const float TopOffset = 96.0f;
    private const float RightMargin = 24.0f;
    private const int TitleFontSize = 15;
    private const int BodyFontSize = 14;
    private const int MaxReasonLength = 80;

    private ColorRect? _background;
    private Label? _titleLabel;
    private RichTextLabel? _bodyLabel;
    private Font? _sharpFont;
    private string _lastText = string.Empty;
    private Vector2I _lastWindowSize;

    public AgentStatusOverlayNode()
    {
        Name = NodeNameValue;
        ProcessMode = ProcessModeEnum.Always;
        TopLevel = true;
        ZIndex = 4096;
        ZAsRelative = false;
        MouseFilter = MouseFilterEnum.Ignore;
        Visible = true;
        Size = new Vector2(PanelWidth, PanelHeight);
        _sharpFont = BuildSharpFont();
        BuildUi();
        UpdatePosition(force: true);
        Refresh(force: true);
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
        UpdatePosition(force: true);
    }

    public override void _Process(double delta)
    {
        UpdatePosition(force: false);
        Refresh(force: false);
    }

    public void RefreshFromState(bool force = false)
    {
        BuildUi();
        UpdatePosition(force: true);
        Refresh(force);
    }

    private void BuildUi()
    {
        if (_bodyLabel is not null)
        {
            return;
        }

        _background = new ColorRect
        {
            Name = "Background",
            MouseFilter = MouseFilterEnum.Ignore,
            Color = new Color(0.03f, 0.06f, 0.10f, 0.78f),
            Position = Vector2.Zero,
            Size = Size,
            Visible = true,
        };
        AddChild(_background);
        AddChild(CreateBorder(new Vector2(0.0f, 0.0f), new Vector2(Size.X, 2.0f)));
        AddChild(CreateBorder(new Vector2(0.0f, Size.Y - 2.0f), new Vector2(Size.X, 2.0f)));
        AddChild(CreateBorder(new Vector2(0.0f, 0.0f), new Vector2(2.0f, Size.Y)));
        AddChild(CreateBorder(new Vector2(Size.X - 2.0f, 0.0f), new Vector2(2.0f, Size.Y)));

        _titleLabel = new Label
        {
            Name = "Title",
            Text = "STS2 Agent",
            Position = new Vector2(12.0f, 8.0f),
            Size = new Vector2(Size.X - 24.0f, 18.0f),
            MouseFilter = MouseFilterEnum.Ignore,
            HorizontalAlignment = HorizontalAlignment.Left,
            VerticalAlignment = VerticalAlignment.Center,
            Visible = true,
        };
        _titleLabel.AddThemeColorOverride("font_color", new Color(0.98f, 0.97f, 0.92f, 0.98f));
        _titleLabel.AddThemeFontSizeOverride("font_size", TitleFontSize);
        _titleLabel.AddThemeConstantOverride("outline_size", 1);
        _titleLabel.AddThemeColorOverride("font_outline_color", new Color(0.0f, 0.0f, 0.0f, 0.75f));
        if (_sharpFont is not null)
        {
            _titleLabel.AddThemeFontOverride("font", _sharpFont);
        }
        AddChild(_titleLabel);

        _bodyLabel = new RichTextLabel
        {
            Name = "Body",
            BbcodeEnabled = false,
            FitContent = false,
            ScrollActive = false,
            MouseFilter = MouseFilterEnum.Ignore,
            AutowrapMode = TextServer.AutowrapMode.WordSmart,
            Position = new Vector2(12.0f, 30.0f),
            Size = new Vector2(Size.X - 24.0f, Size.Y - 40.0f),
            Visible = true,
        };
        _bodyLabel.AddThemeColorOverride("default_color", new Color(0.95f, 0.96f, 0.97f, 0.95f));
        _bodyLabel.AddThemeFontSizeOverride("normal_font_size", BodyFontSize);
        _bodyLabel.AddThemeConstantOverride("line_separation", -2);
        if (_sharpFont is not null)
        {
            _bodyLabel.AddThemeFontOverride("normal_font", _sharpFont);
        }
        AddChild(_bodyLabel);
    }

    private void UpdatePosition(bool force)
    {
        var windowSize = DisplayServer.WindowGetSize();
        if (!force && windowSize == _lastWindowSize)
        {
            return;
        }

        _lastWindowSize = windowSize;
        Position = new Vector2(
            Math.Max(16.0f, windowSize.X - PanelWidth - RightMargin),
            TopOffset);
    }

    private void Refresh(bool force)
    {
        if (_bodyLabel is null)
        {
            return;
        }

        var text = BuildOverlayText(AgentStatusStateStore.GetCurrent());
        if (!force && string.Equals(text, _lastText, StringComparison.Ordinal))
        {
            return;
        }

        _bodyLabel.Text = text;
        _lastText = text;
    }

    private Font BuildSharpFont()
    {
        var source = ThemeDB.Singleton.FallbackFont ?? ThemeDB.FallbackFont;
        var windowSize = DisplayServer.WindowGetSize();
        var viewportWidthVariant = ProjectSettings.GetSetting("display/window/size/viewport_width");
        var viewportWidth = viewportWidthVariant.VariantType == Variant.Type.Int ? (int)viewportWidthVariant : 1920;
        var oversampling = viewportWidth > 0 ? windowSize.X / (float)viewportWidth * 2.0f : 2.0f;
        return WithSharpSettings(source, Math.Max(1.0f, oversampling));
    }

    private static Font WithSharpSettings(Font source, float oversampling)
    {
        var duplicate = (Font)source.Duplicate();

        switch (duplicate)
        {
            case FontFile fontFile:
                fontFile.Oversampling = oversampling;
                break;
            case SystemFont systemFont:
                systemFont.MultichannelSignedDistanceField = true;
                break;
        }

        var fallbacks = duplicate.Fallbacks;
        for (var i = 0; i < fallbacks.Count; i++)
        {
            if (fallbacks[i] is Font font)
            {
                fallbacks[i] = WithSharpSettings(font, oversampling);
            }
        }

        duplicate.Fallbacks = fallbacks;
        return duplicate;
    }

    private static ColorRect CreateBorder(Vector2 position, Vector2 size)
    {
        return new ColorRect
        {
            MouseFilter = MouseFilterEnum.Ignore,
            Color = new Color(0.55f, 0.66f, 0.78f, 0.65f),
            Position = position,
            Size = size,
            Visible = true,
        };
    }

    private static string BuildOverlayText(AgentStatusResponse snapshot)
    {
        if (snapshot.Empty)
        {
            return "status: idle\nphase: idle\nwaiting for agent status";
        }

        var builder = new StringBuilder();
        builder.Append("status: ").Append(snapshot.Status);
        if (snapshot.Stale && !string.IsNullOrWhiteSpace(snapshot.SourceStatus))
        {
            builder.Append(" (").Append(snapshot.SourceStatus).Append(')');
        }
        builder.AppendLine();

        builder.Append("phase: ").Append(snapshot.Phase ?? "unknown").AppendLine();
        builder.Append("action: ").Append(snapshot.ActionLabel ?? snapshot.ActionId ?? "none").AppendLine();

        if (!string.IsNullOrWhiteSpace(snapshot.Confidence) || snapshot.Turn is not null || snapshot.Step is not null)
        {
            builder.Append("meta: ");
            if (!string.IsNullOrWhiteSpace(snapshot.Confidence))
            {
                builder.Append("conf ").Append(snapshot.Confidence);
            }
            if (snapshot.Turn is not null || snapshot.Step is not null)
            {
                if (!string.IsNullOrWhiteSpace(snapshot.Confidence))
                {
                    builder.Append("  ");
                }
                builder.Append("turn ").Append(snapshot.Turn?.ToString() ?? "-").Append('/').Append(snapshot.Step?.ToString() ?? "-");
            }
            builder.AppendLine();
        }

        var reason = Truncate(snapshot.Reason, MaxReasonLength);
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

        var normalized = value
            .Replace("\r\n", "\n", StringComparison.Ordinal)
            .Replace('\r', '\n')
            .Replace('\n', ' ')
            .Trim();

        if (normalized.Length <= limit)
        {
            return normalized;
        }

        return normalized[..Math.Max(0, limit - 1)].TrimEnd() + "...";
    }
}
#endif
