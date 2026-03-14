using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Sts2TypeDump;

internal static class Program
{
    public static int Main(string[] args)
    {
        var managedDir = GetArg(args, "--managed-dir");
        var typeName = GetArg(args, "--type");
        var outPath = GetArgOrNull(args, "--out");
        if (string.IsNullOrWhiteSpace(managedDir) || string.IsNullOrWhiteSpace(typeName))
        {
            Console.Error.WriteLine("Usage: dotnet run --project tools/Sts2TypeDump -- --managed-dir <dir> --type <Full.Type.Name> [--out <path>]");
            return 2;
        }

        managedDir = Path.GetFullPath(managedDir);
        var sts2Path = Path.Combine(managedDir, "sts2.dll");
        if (!File.Exists(sts2Path))
        {
            Console.Error.WriteLine($"sts2.dll not found: {sts2Path}");
            return 2;
        }

        var alc = new AssemblyLoadContext("sts2_dump", isCollectible: true);
        alc.Resolving += (_, name) =>
        {
            var candidate = Path.Combine(managedDir, name.Name + ".dll");
            return File.Exists(candidate) ? alc.LoadFromAssemblyPath(candidate) : null;
        };

        try
        {
            var assembly = alc.LoadFromAssemblyPath(sts2Path);
            var type = assembly.GetType(typeName, throwOnError: false, ignoreCase: false);
            if (type is null)
            {
                Console.Error.WriteLine($"Type not found: {typeName}");
                return 1;
            }

            var payload = new TypeDump(
                FullName: type.FullName ?? type.Name,
                BaseType: type.BaseType?.FullName,
                Interfaces: type.GetInterfaces().Select(i => i.FullName ?? i.Name).Distinct().OrderBy(x => x).ToArray(),
                Fields: type.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)
                    .Select(f => new MemberDump(f.Name, f.FieldType.FullName ?? f.FieldType.Name, Flags(f.IsPublic, f.IsStatic)))
                    .OrderBy(m => m.Name)
                    .ToArray(),
                Properties: type.GetProperties(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)
                    .Where(p => p.GetIndexParameters().Length == 0)
                    .Select(p => new MemberDump(p.Name, p.PropertyType.FullName ?? p.PropertyType.Name, Flags(IsPublic(p), IsStatic(p))))
                    .OrderBy(m => m.Name)
                    .ToArray(),
                Methods: type.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)
                    .Where(m => !m.IsSpecialName)
                    .Select(m => new MethodDump(
                        Name: m.Name,
                        ReturnType: m.ReturnType.FullName ?? m.ReturnType.Name,
                        Parameters: m.GetParameters().Select(p => new ParameterDump(p.Name ?? "arg", p.ParameterType.FullName ?? p.ParameterType.Name)).ToArray(),
                        Flags: Flags(m.IsPublic, m.IsStatic)))
                    .OrderBy(m => m.Name)
                    .ThenBy(m => m.Parameters.Length)
                    .ToArray());

            var jsonOptions = new JsonSerializerOptions(JsonSerializerDefaults.Web)
            {
                WriteIndented = true,
                DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
            };

            var json = JsonSerializer.Serialize(payload, jsonOptions);
            if (!string.IsNullOrWhiteSpace(outPath))
            {
                outPath = Path.GetFullPath(outPath);
                Directory.CreateDirectory(Path.GetDirectoryName(outPath)!);
                File.WriteAllText(outPath, json + "\n", new System.Text.UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
                Console.WriteLine(outPath);
                return 0;
            }

            Console.WriteLine(json);
            return 0;
        }
        catch (ReflectionTypeLoadException ex)
        {
            Console.Error.WriteLine(ex.Message);
            foreach (var loaderEx in ex.LoaderExceptions.Where(e => e is not null).Take(10))
            {
                Console.Error.WriteLine("LoaderException: " + loaderEx!.Message);
            }
            return 1;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.ToString());
            return 1;
        }
        finally
        {
            alc.Unload();
        }
    }

    private static string GetArg(string[] args, string name)
    {
        var value = GetArgOrNull(args, name);
        return value ?? string.Empty;
    }

    private static string? GetArgOrNull(string[] args, string name)
    {
        for (var i = 0; i < args.Length; i++)
        {
            if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
            {
                return args[i + 1];
            }
        }
        return null;
    }

    private static string Flags(bool isPublic, bool isStatic)
    {
        return $"{(isPublic ? "public" : "nonpublic")},{(isStatic ? "static" : "instance")}";
    }

    private static bool IsStatic(PropertyInfo property)
    {
        var getter = property.GetGetMethod(nonPublic: true);
        var setter = property.GetSetMethod(nonPublic: true);
        return getter?.IsStatic == true || setter?.IsStatic == true;
    }

    private static bool IsPublic(PropertyInfo property)
    {
        var getter = property.GetGetMethod(nonPublic: true);
        var setter = property.GetSetMethod(nonPublic: true);
        return getter?.IsPublic == true || setter?.IsPublic == true;
    }

    private sealed record TypeDump(
        string FullName,
        string? BaseType,
        string[] Interfaces,
        MemberDump[] Fields,
        MemberDump[] Properties,
        MethodDump[] Methods);

    private sealed record MemberDump(string Name, string Type, string Flags);

    private sealed record MethodDump(string Name, string ReturnType, ParameterDump[] Parameters, string Flags);

    private sealed record ParameterDump(string Name, string Type);
}
