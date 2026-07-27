import TopBar from "@/components/terminal/TopBar";
import ChartPanel from "@/components/terminal/ChartPanel";

export default function Terminal() {
  return (
    <div className="flex h-screen w-full flex-col bg-[#000000] text-foreground overflow-hidden">
      <TopBar />
      <div className="flex-1 overflow-hidden">
        <ChartPanel />
      </div>
    </div>
  );
}
