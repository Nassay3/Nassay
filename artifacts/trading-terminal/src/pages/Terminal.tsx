import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import TopBar from "@/components/terminal/TopBar";
import OrderBook from "@/components/terminal/OrderBook";
import RecentTrades from "@/components/terminal/RecentTrades";
import ChartPanel from "@/components/terminal/ChartPanel";

export default function Terminal() {
  return (
    <div className="flex h-screen w-full flex-col bg-[#000000] text-foreground overflow-hidden">
      <TopBar />
      <div className="flex-1 overflow-hidden">
        <ResizablePanelGroup direction="horizontal">

          {/* Center - Chart */}
          <ResizablePanel defaultSize={75} className="flex flex-col">
            <ChartPanel />
          </ResizablePanel>

          <ResizableHandle className="hidden lg:flex w-[1px] bg-[#161616] hover:bg-[#2962ff] transition-colors" />

          {/* Right Sidebar - OrderBook & Trades */}
          <ResizablePanel defaultSize={25} minSize={15} maxSize={35} className="border-l border-[#161616] bg-[#080808] hidden lg:flex flex-col">
            <ResizablePanelGroup direction="vertical">
              <ResizablePanel defaultSize={60} minSize={30}>
                <OrderBook />
              </ResizablePanel>
              <ResizableHandle className="h-[1px] bg-[#161616] hover:bg-[#2962ff] transition-colors" />
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
