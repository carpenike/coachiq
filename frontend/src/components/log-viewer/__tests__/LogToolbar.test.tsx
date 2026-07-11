import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLogViewer } from "../useLogViewer";
import { LogToolbar } from "../LogToolbar";

vi.mock("../useLogViewer", () => ({ useLogViewer: vi.fn() }));
vi.mock("../AdvancedLogSearch", () => ({ AdvancedLogSearch: () => <div /> }));
vi.mock("../EnhancedLogLevelFilter", () => ({ EnhancedLogLevelFilter: () => <div /> }));
vi.mock("../LogLevelFilter", () => ({ LogLevelFilter: () => <div /> }));
vi.mock("../ModuleFilter", () => ({ ModuleFilter: () => <div /> }));
vi.mock("../LogExportActions", () => ({ LogExportActions: () => <div /> }));
vi.mock("../LogPerformanceMonitor", () => ({ LogPerformanceMonitor: () => <div /> }));

const mockedUseLogViewer = vi.mocked(useLogViewer);

function logViewerValue(connectionStatus: "connected" | "disconnected") {
  return {
    logs: [],
    rawLogs: [],
    loading: false,
    filters: {},
    updateFilters: vi.fn(),
    clearLogs: vi.fn(),
    pauseStream: vi.fn(),
    resumeStream: vi.fn(),
    isPaused: false,
    fetchMore: vi.fn(),
    hasMore: false,
    mode: "live" as const,
    setMode: vi.fn(),
    connectionStatus,
    reconnect: vi.fn(),
    error: null,
    clearError: vi.fn(),
  };
}

describe("LogToolbar disconnected controls", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows one reconnect action and hides irrelevant stream controls", () => {
    mockedUseLogViewer.mockReturnValue(logViewerValue("disconnected"));

    render(<LogToolbar />);

    expect(screen.getAllByRole("button", { name: "Reconnect live stream" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Pause log stream" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear logs" })).not.toBeInTheDocument();
  });

  it("restores live controls once the stream is connected", () => {
    mockedUseLogViewer.mockReturnValue(logViewerValue("connected"));

    render(<LogToolbar />);

    expect(screen.getByRole("button", { name: "Pause log stream" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear logs" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Reconnect live stream" })).not.toBeInTheDocument();
  });
});
