namespace AgentEye.Core.Config;

/// <summary>配置不可用。调用方据此提示用户,不要静默吞掉。</summary>
public class ConfigError : Exception
{
    public ConfigError(string message) : base(message) { }
}

/// <summary>配置的 schema_version 高于本程序支持的版本。</summary>
public class ConfigVersionError : ConfigError
{
    public ConfigVersionError(string message) : base(message) { }
}

/// <summary>拒绝把明文 key 写进 config.json。</summary>
public class PlaintextKeyError : ConfigError
{
    public PlaintextKeyError(string message) : base(message) { }
}
