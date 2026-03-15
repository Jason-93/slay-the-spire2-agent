using Sts2Mod.StateBridge.Contracts;
using Sts2Mod.StateBridge.Server;
using Xunit;

namespace Sts2Mod.StateBridge.Tests;

public sealed class AgentStatusStateStoreTests
{
    [Fact]
    public void Update_AppendsHistoryEntries()
    {
        AgentStatusStateStore.Clear();

        AgentStatusStateStore.Update(new AgentStatusUpdateRequest(
            SessionId: "sess-1",
            Phase: "combat",
            Status: "thinking",
            UpdatedAt: "2026-03-15T10:00:00Z",
            Reason: "正在分析当前局面",
            Detail: "准备决策"));

        var response = AgentStatusStateStore.Update(new AgentStatusUpdateRequest(
            SessionId: "sess-1",
            Phase: "combat",
            Status: "planned",
            UpdatedAt: "2026-03-15T10:00:01Z",
            ActionLabel: "Play 防御",
            Reason: "先补格挡",
            Detail: "敌人即将攻击",
            Turn: 1,
            Step: 2));

        Assert.NotNull(response.History);
        Assert.Equal(2, response.History.Count);
        Assert.Equal("thinking", response.History[0].Status);
        Assert.Equal("planned", response.History[1].Status);
        Assert.Equal("Play 防御", response.History[1].ActionLabel);
        Assert.Equal("先补格挡", response.History[1].Reason);
    }

    [Fact]
    public void Update_MergesStatusTransitionsForSameDecision()
    {
        AgentStatusStateStore.Clear();

        AgentStatusStateStore.Update(new AgentStatusUpdateRequest(
            SessionId: "sess-1",
            Phase: "combat",
            Status: "planned",
            UpdatedAt: "2026-03-15T10:00:00Z",
            ActionLabel: "Play 防御",
            Reason: "先补格挡",
            Detail: "敌人即将攻击",
            Turn: 1,
            Step: 2));

        AgentStatusStateStore.Update(new AgentStatusUpdateRequest(
            SessionId: "sess-1",
            Phase: "combat",
            Status: "submitted",
            UpdatedAt: "2026-03-15T10:00:01Z",
            ActionLabel: "Play 防御",
            Reason: "先补格挡",
            Detail: "敌人即将攻击",
            Turn: 1,
            Step: 2));

        var response = AgentStatusStateStore.Update(new AgentStatusUpdateRequest(
            SessionId: "sess-1",
            Phase: "combat",
            Status: "accepted",
            UpdatedAt: "2026-03-15T10:00:02Z",
            ActionLabel: "Play 防御",
            Reason: "先补格挡",
            Detail: "敌人即将攻击",
            Turn: 1,
            Step: 2));

        Assert.NotNull(response.History);
        Assert.Single(response.History);
        Assert.Equal("accepted", response.History[0].Status);
        Assert.Equal("Play 防御", response.History[0].ActionLabel);
    }

    [Fact]
    public void Clear_RemovesHistory()
    {
        AgentStatusStateStore.Clear();
        AgentStatusStateStore.Update(new AgentStatusUpdateRequest(
            SessionId: "sess-1",
            Phase: "combat",
            Status: "thinking",
            UpdatedAt: "2026-03-15T10:00:00Z",
            Reason: "正在分析"));

        var response = AgentStatusStateStore.Clear();

        Assert.True(response.Empty);
        Assert.NotNull(response.History);
        Assert.Empty(response.History);
    }
}
