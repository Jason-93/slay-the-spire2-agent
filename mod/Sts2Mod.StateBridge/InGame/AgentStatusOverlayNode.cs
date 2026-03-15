#if STS2_REAL_RUNTIME
using Godot;
using Sts2Mod.StateBridge.Contracts;
using Sts2Mod.StateBridge.Server;
using System.Text;

namespace Sts2Mod.StateBridge.InGame;

internal sealed partial class AgentStatusOverlayNode : Control
{
    public const string NodeNameValue = "Sts2AgentStatusOverlay";

    private const float PanelWidth = 412.0f;
    private const float PanelHeight = 244.0f;
    private const float TopOffset = 84.0f;
    private const float RightMargin = 20.0f;
    private const int TitleFontSize = 14;
    private const int BodyFontSize = 12;
    private const int MaxSummaryLength = 72;
    private const int MaxDetailLength = 240;
    private const int MaxHistorySummaryLength = 44;
    private const int MaxHistoryEntries = 6;

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
            ScrollActive = true,
            MouseFilter = MouseFilterEnum.Ignore,
            AutowrapMode = TextServer.AutowrapMode.WordSmart,
            Position = new Vector2(12.0f, 30.0f),
            Size = new Vector2(Size.X - 24.0f, Size.Y - 42.0f),
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
        _bodyLabel.ScrollToLine(Math.Max(0, _bodyLabel.GetLineCount() - 1));
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
            return "状态: idle\n阶段: idle\n等待 agent 状态同步";
        }

        var builder = new StringBuilder();
        builder.Append("状态: ").Append(snapshot.Status);
        if (snapshot.Stale && !string.IsNullOrWhiteSpace(snapshot.SourceStatus))
        {
            builder.Append(" (").Append(snapshot.SourceStatus).Append(')');
        }
        builder.AppendLine();

        builder.Append("阶段: ").Append(snapshot.Phase ?? "unknown").AppendLine();
        builder.Append("动作: ").Append(snapshot.ActionLabel ?? snapshot.ActionId ?? "none").AppendLine();

        if (!string.IsNullOrWhiteSpace(snapshot.Confidence) || snapshot.Turn is not null || snapshot.Step is not null)
        {
            builder.Append("元信息: ");
            if (!string.IsNullOrWhiteSpace(snapshot.Confidence))
            {
                builder.Append("置信 ").Append(snapshot.Confidence);
            }
            if (snapshot.Turn is not null || snapshot.Step is not null)
            {
                if (!string.IsNullOrWhiteSpace(snapshot.Confidence))
                {
                    builder.Append("  ");
                }
                builder.Append("回合 ").Append(snapshot.Turn?.ToString() ?? "-").Append('/').Append(snapshot.Step?.ToString() ?? "-");
            }
            builder.AppendLine();
        }

        var summary = NormalizeSingleLine(snapshot.Reason, MaxSummaryLength);
        if (!string.IsNullOrWhiteSpace(summary))
        {
            builder.Append("摘要: ").Append(summary).AppendLine();
        }

        var detail = NormalizeMultiline(snapshot.Detail, MaxDetailLength);
        if (!string.IsNullOrWhiteSpace(detail))
        {
            builder.Append("思路: ").Append(detail.Replace("\n", "\n      ", StringComparison.Ordinal)).AppendLine();
        }

        var history = snapshot.History ?? [];
        if (history.Count > 1)
        {
            builder.AppendLine();
            builder.AppendLine("最近决策:");
            var start = Math.Max(0, history.Count - MaxHistoryEntries);
            for (var index = start; index < history.Count; index++)
            {
                var entry = history[index];
                builder.Append("  ");
                builder.Append(index == history.Count - 1 ? "-> " : "· ");
                builder.Append(FormatHistoryEntry(entry));
                if (index < history.Count - 1)
                {
                    builder.AppendLine();
                }
            }
        }

        return builder.ToString().TrimEnd();
    }

    private static string FormatHistoryEntry(AgentStatusHistoryEntry entry)
    {
        var builder = new StringBuilder();
        builder.Append(entry.Status);
        if (!string.IsNullOrWhiteSpace(entry.ActionLabel))
        {
            builder.Append(" / ").Append(entry.ActionLabel);
        }

        var summary = NormalizeSingleLine(entry.Reason, MaxHistorySummaryLength);
        if (!string.IsNullOrWhiteSpace(summary))
        {
            builder.Append(" / ").Append(summary);
        }

        if (entry.Turn is not null || entry.Step is not null)
        {
            builder.Append(" / ");
            builder.Append(entry.Turn?.ToString() ?? "-");
            builder.Append('/');
            builder.Append(entry.Step?.ToString() ?? "-");
        }

        return builder.ToString();
    }

    private static string NormalizeSingleLine(string? value, int limit)
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

    private static string NormalizeMultiline(string? value, int limit)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        var lines = value
            .Replace("\r\n", "\n", StringComparison.Ordinal)
            .Replace('\r', '\n')
            .Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        if (lines.Length == 0)
        {
            return string.Empty;
        }

        var normalized = string.Join("\n", lines);
        if (normalized.Length <= limit)
        {
            return normalized;
        }

        return normalized[..Math.Max(0, limit - 1)].TrimEnd() + "...";
    }
}
#endif
