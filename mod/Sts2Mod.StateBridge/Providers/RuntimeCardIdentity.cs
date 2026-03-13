using System.Reflection;
using System.Security.Cryptography;
using System.Text;

namespace Sts2Mod.StateBridge.Providers;

internal static class RuntimeCardIdentity
{
    public static string CreateCardId(object? card, int handIndex)
    {
        var instanceKey = ResolveInstanceKey(card);
        if (!string.IsNullOrWhiteSpace(instanceKey))
        {
            return $"card-{Hash($"{instanceKey}|slot:{handIndex}")}";
        }

        var modelKey = ResolveModelKey(card) ?? "unknown-card";
        return $"card-{Hash($"{modelKey}|slot:{handIndex}")}";
    }

    private static string? ResolveInstanceKey(object? card)
    {
        foreach (var memberName in new[] { "InstanceId", "RuntimeId", "CombatId", "CardId", "UniqueId", "Guid", "Id" })
        {
            var text = ConvertToStableText(GetMemberValue(card, memberName));
            if (!string.IsNullOrWhiteSpace(text))
            {
                return $"instance:{memberName}:{text}";
            }
        }

        return null;
    }

    private static string? ResolveModelKey(object? card)
    {
        foreach (var memberName in new[] { "ModelId", "DebugName", "InternalName", "Name", "Title" })
        {
            var text = ConvertToStableText(GetMemberValue(card, memberName));
            if (!string.IsNullOrWhiteSpace(text))
            {
                return $"model:{memberName}:{text}";
            }
        }

        return ConvertToStableText(card?.GetType().FullName);
    }

    private static string? ConvertToStableText(object? value)
    {
        if (value is null)
        {
            return null;
        }

        if (value is string text)
        {
            return string.IsNullOrWhiteSpace(text) ? null : text;
        }

        if (value is Guid guid)
        {
            return guid.ToString("N");
        }

        if (value is IFormattable formattable)
        {
            return formattable.ToString(null, null);
        }

        var textValue = value.ToString();
        if (string.IsNullOrWhiteSpace(textValue))
        {
            return null;
        }

        var type = value.GetType();
        if (string.Equals(textValue, type.FullName, StringComparison.Ordinal) ||
            string.Equals(textValue, type.Name, StringComparison.Ordinal))
        {
            return null;
        }

        return textValue;
    }

    private static object? GetMemberValue(object? target, string memberName)
    {
        if (target is null)
        {
            return null;
        }

        var type = target.GetType();
        const BindingFlags flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
        var property = type.GetProperty(memberName, flags);
        if (property is not null && property.GetIndexParameters().Length == 0)
        {
            try
            {
                return property.GetValue(target);
            }
            catch
            {
                return null;
            }
        }

        var field = type.GetField(memberName, flags);
        if (field is null)
        {
            return null;
        }

        try
        {
            return field.GetValue(target);
        }
        catch
        {
            return null;
        }
    }

    private static string Hash(string value)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(value));
        return BitConverter.ToUInt32(bytes, 0).ToString("x8");
    }
}
