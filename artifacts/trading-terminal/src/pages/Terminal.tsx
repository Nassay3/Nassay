import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import TopBar from "@/components/terminal/TopBar";
import Watchlist from "@/components/terminal/Watchlist";
import OrderBook from "@/components/terminal/OrderBook";
import RecentTrades from "@/components/terminal/RecentTrades";
import ChartPanel from "@/components/terminal/ChartPanel";

export default function Terminal() {
  return (
    <div className="flex h-screen w-full flex-col bg-background text-foreground overflow-hidden">
      <TopBar />
      <div className="flex-1 overflow-hidden">
        <ResizablePanelGroup direction="horizontal">
          
          {/* Left Sidebar - Watchlist */}
          <ResizablePanel defaultSize={20} minSize={15} maxSize={30} className="border-r border-border bg-card hidden md:block">
            <Watchlist />
          </ResizablePanel>
          
          <ResizableHandle className="hidden md:flex w-[1px] bg-border hover:bg-primary transition-colors" />
          
          {/* Center - Chart */}
          <ResizablePanel defaultSize={60} className="flex flex-col">
            <ChartPanel />
          </ResizablePanel>
          
          <ResizableHandle className="hidden lg:flex w-[1px] bg-border hover:bg-primary transition-colors" />
          
          {/* Right Sidebar - OrderBook & Trades */}
          <ResizablePanel defaultSize={20} minSize={15} maxSize={30} className="border-l border-border bg-card hidden lg:flex flex-col">
            <ResizablePanelGroup direction="vertical">
              <ResizablePanel defaultSize={60} minSize={30}>
                <OrderBook />
              </ResizablePanel>
              <ResizableHandle className="h-[1px] bg-border hover:bg-primary transition-colors" />
              <ResizablePanel defaultSize={40} minSize={20}>
                <RecentTrades />
              </ResizablePanel>
            </ResizablePanelGroup>
          </ResizablePanel>

        </ResizablePanelGroup>
      </div>
    </div>
  );
}
