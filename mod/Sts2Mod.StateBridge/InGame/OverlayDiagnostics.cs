#if STS2_REAL_RUNTIME
using Godot;
using System.Text;

namespace Sts2Mod.StateBridge.InGame;

internal static class OverlayDiagnostics
{
    private static readonly object Gate = new();
    private static readonly string LogPath = Path.Combine(AppContext.BaseDirectory, "mods", "Sts2Mod.StateBridge", "agent-status-overlay.log");

    public static void Log(string message)
    {
        lock (Gate)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(LogPath)!);
            File.AppendAllText(
                LogPath,
                $"[{DateTimeOffset.Now:O}] {message}{System.Environment.NewLine}",
                new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
        }
    }

    public static void DumpNodeChain(string title, Node? node)
    {
        if (node is null)
        {
            Log($"{title}: <null>");
            return;
        }

        var parts = new List<string>();
        Node? current = node;
        while (current is not null)
        {
            parts.Add($"{current.Name}<{current.GetType().FullName}>");
            current = current.GetParent();
        }

        Log($"{title}: {string.Join(" <- ", parts)}");
    }

    public static void DumpTree(Node? root, int maxDepth = 3, int maxNodes = 80)
    {
        if (root is null)
        {
            Log("tree: <null>");
            return;
        }

        var lines = new List<string>();
        var queue = new Queue<(Node Node, int Depth)>();
        queue.Enqueue((root, 0));

        while (queue.Count > 0 && lines.Count < maxNodes)
        {
            var (node, depth) = queue.Dequeue();
            var indent = new string(' ', depth * 2);
            lines.Add($"{indent}- {node.Name} <{node.GetType().FullName}>");
            if (depth >= maxDepth)
            {
                continue;
            }

            foreach (var child in node.GetChildren())
            {
                if (child is Node childNode)
                {
                    queue.Enqueue((childNode, depth + 1));
                }
            }
        }

        Log("tree dump begin");
        foreach (var line in lines)
        {
            Log(line);
        }
        Log("tree dump end");
    }
}
#endif
