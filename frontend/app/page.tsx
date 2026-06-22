import Link from "next/link";
import {
  ArrowRight,
  ShieldCheck,
  Calculator,
  FileText,
  TrendingUp,
  PieChart as PieChartIcon,
  UploadCloud,
  CheckCircle,
  Sparkles,
  Activity,
} from "lucide-react";
import Reveal from "./components/Reveal";

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50 grid-bg text-gray-900 selection:bg-blue-100 flex flex-col relative overflow-hidden">

      {/* Decorative Glow Orbs — now with floating animation */}
      <div aria-hidden="true" className="glow-orb top-[-200px] left-[-150px] animate-float" />
      <div aria-hidden="true" className="glow-orb top-[35%] right-[-200px] animate-float-slow" />
      <div aria-hidden="true" className="glow-orb bottom-[10%] left-[30%] opacity-10 animate-float" />

      {/* ─── Navbar ─── */}
      <nav className="fixed top-0 w-full z-50 glass-header">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-2 font-bold text-lg tracking-tight text-gray-900">
            <Activity className="w-5 h-5 text-blue-600" />
            <span>FinTrace</span>
          </div>
          <div className="flex items-center gap-3 sm:gap-6">
            <Link
              href="/login"
              className="text-sm font-semibold text-gray-600 hover:text-blue-600 transition-colors"
            >
              Sign In
            </Link>
            <Link
              href="/register"
              className="text-sm font-semibold bg-blue-600 text-white px-4 sm:px-5 py-2.5 rounded-lg hover:bg-blue-700 shadow-md hover:shadow-blue-500/20 hover:-translate-y-0.5 transition-all duration-200"
            >
              Get Started<span className="hidden sm:inline"> — Free</span>
            </Link>
          </div>
        </div>
      </nav>

      {/* ─── Hero Section ─── */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 pt-32 pb-24 relative z-10 flex flex-col items-center">

        {/* Badge — staggered entrance */}
        <div className="animate-hero animate-hero-d1 inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-blue-200 bg-blue-50 text-blue-700 text-xs font-semibold mb-8 shadow-sm">
          <Sparkles className="w-3.5 h-3.5 text-blue-500" />
          <span>NSE / BSE · FIFO Tax Engine · Real-Time XIRR</span>
        </div>

        {/* Headline */}
        <h1 className="animate-hero animate-hero-d2 text-4xl sm:text-6xl md:text-7xl font-extrabold tracking-tight text-center leading-tight max-w-4xl text-gray-900">
          Track Portfolio Returns<br />with{" "}
          <span className="text-gradient-blue">Absolute Precision.</span>
        </h1>

        {/* Subheadline */}
        <p className="animate-hero animate-hero-d3 mt-6 text-lg sm:text-xl text-gray-500 text-center max-w-2xl leading-relaxed">
          Upload your broker CSV, and FinTrace calculates your real XIRR, automates FIFO-based STCG &amp; LTCG tracking, and stores every transaction in an immutable audit ledger.
        </p>

        {/* Hero Stat Strip */}
        <div className="animate-hero animate-hero-d4 mt-10 flex flex-wrap items-center justify-center gap-6 text-sm">
          {[
            { label: "Calculation Method", value: "XIRR (Annualised)" },
            { label: "Tax Method", value: "FIFO Standard" },
            { label: "Jurisdictions", value: "India (IN)" },
            { label: "Data Integrity", value: "Append-Only Ledger" },
          ].map((stat) => (
            <div
              key={stat.label}
              className="flex flex-col items-center bg-white border border-gray-200 rounded-xl px-5 py-3 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-200"
            >
              <span className="font-extrabold text-blue-600 text-base">{stat.value}</span>
              <span className="text-gray-400 text-xs mt-0.5">{stat.label}</span>
            </div>
          ))}
        </div>

        {/* CTA Buttons */}
        <div className="animate-hero animate-hero-d5 mt-10 flex flex-col items-center gap-3">
          <Link
            href="/register"
            className="group flex items-center gap-2 bg-blue-600 text-white px-8 py-4 rounded-lg font-semibold text-base hover:bg-blue-700 shadow-lg hover:shadow-blue-500/20 hover:-translate-y-0.5 transition-all duration-200"
          >
            Create Free Account
            <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
          </Link>
          <p className="text-sm text-gray-400">
            Already have an account?{" "}
            <Link href="/login" className="text-blue-600 hover:underline font-medium">
              Sign in
            </Link>
          </p>
        </div>

        {/* ─── Dashboard Preview Mockup ─── */}
        <div className="animate-hero animate-hero-d6 w-full max-w-5xl mt-20 border border-gray-200 rounded-xl shadow-2xl shadow-gray-200/70 bg-white overflow-hidden transition-all duration-300 hover:border-blue-200 hover:shadow-blue-100">

          {/* Mockup Titlebar */}
          <div className="bg-gray-50/80 border-b border-gray-200 px-5 py-3 flex justify-between items-center">
            <div className="flex items-center space-x-2">
              <Activity className="w-4 h-4 text-blue-600" />
              <span className="font-bold text-gray-800 text-xs sm:text-sm">
                FinTrace / My Core Holdings
              </span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-700 border border-blue-200">
                IN · FIFO
              </span>
            </div>
            <div className="flex gap-1.5">
              <span className="w-3 h-3 rounded-full bg-red-400/80" />
              <span className="w-3 h-3 rounded-full bg-yellow-400/80" />
              <span className="w-3 h-3 rounded-full bg-green-400/80" />
            </div>
          </div>

          {/* Inner Grid */}
          <div className="p-5 grid grid-cols-1 lg:grid-cols-3 gap-5 bg-gray-50/30">

            {/* Left: Stats + Upload + Tax */}
            <div className="lg:col-span-1 space-y-4">

              {/* Key Metrics */}
              <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm">
                <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider flex items-center gap-1.5 mb-4">
                  <TrendingUp className="w-3.5 h-3.5 text-blue-600" /> Key Metrics
                </h3>
                <div className="space-y-4">
                  <div>
                    <p className="text-[10px] text-gray-400 font-semibold uppercase tracking-wider">XIRR (Annualised Return)</p>
                    <p className="text-3xl font-extrabold text-blue-600 mt-0.5">24.85%</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 pt-3 border-t border-gray-100">
                    <div>
                      <p className="text-[10px] text-gray-400 font-semibold">Invested</p>
                      <p className="text-sm font-bold text-gray-900 flex items-center gap-0.5">
                        ₹8,45,000
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] text-gray-400 font-semibold">Current Value</p>
                      <p className="text-sm font-bold text-green-600 flex items-center gap-0.5">
                        ₹10,54,920
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* CSV Upload */}
              <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm">
                <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider flex items-center gap-1.5 mb-3">
                  <UploadCloud className="w-3.5 h-3.5 text-blue-600" /> Data Ingestion
                </h3>
                <p className="text-xs text-gray-400 mb-3">
                  Upload your broker CSV to sync transaction ledger.
                </p>
                <div className="border-2 border-dashed border-gray-200 rounded-lg p-5 text-center bg-gray-50 hover:bg-gray-50/80 transition-colors">
                  <UploadCloud className="w-7 h-7 text-gray-400 mx-auto mb-2" />
                  <p className="text-xs font-semibold text-gray-700">transactions_2026.csv</p>
                  <p className="text-[10px] text-green-600 flex items-center justify-center gap-1 mt-1 font-medium">
                    <CheckCircle className="w-3 h-3" /> Ingestion complete · 42 records
                  </p>
                </div>
              </div>

              {/* Tax Compliance */}
              <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm">
                <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider flex items-center gap-1.5 mb-3">
                  <FileText className="w-3.5 h-3.5 text-blue-600" /> Tax Compliance (FIFO)
                </h3>
                <div className="space-y-2.5 mb-4">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-500 font-medium">Realized STCG</span>
                    <span className="font-bold text-red-500 bg-red-50 px-2 py-0.5 rounded">
                      ₹45,210.00
                    </span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-500 font-medium">Realized LTCG</span>
                    <span className="font-bold text-green-600 bg-green-50 px-2 py-0.5 rounded">
                      ₹1,64,300.00
                    </span>
                  </div>
                </div>
                <div className="w-full bg-blue-600 text-white py-2 rounded-md text-xs font-bold flex items-center justify-center gap-1.5">
                  <FileText className="w-3.5 h-3.5" /> Download Tax Report (PDF)
                </div>
              </div>
            </div>

            {/* Right: Charts */}
            <div className="lg:col-span-2 space-y-4">

              {/* Growth Line Chart */}
              <div className="min-h-60 bg-white p-5 rounded-lg border border-gray-200 shadow-sm">
                <div className="mb-2 flex flex-col items-start justify-between gap-2 sm:flex-row sm:items-center">
                  <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider flex items-center gap-1.5">
                    <TrendingUp className="w-3.5 h-3.5 text-blue-600" /> Portfolio Growth (YTD)
                  </h3>
                  <span className="text-xs font-bold text-green-600 bg-green-50 border border-green-200 px-2 py-0.5 rounded-full">
                    +₹2,09,920 (+24.85%)
                  </span>
                </div>
                <div className="h-[170px] w-full relative">
                  <svg className="w-full h-full" viewBox="0 0 400 140" preserveAspectRatio="none" role="img" aria-label="Portfolio value from January to June 2026">
                    <defs>
                      <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.15" />
                        <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
                      </linearGradient>
                    </defs>
                    {/* Grid */}
                    <line x1="0" y1="35" x2="400" y2="35" stroke="#f3f4f6" strokeWidth="1" />
                    <line x1="0" y1="70" x2="400" y2="70" stroke="#f3f4f6" strokeWidth="1" />
                    <line x1="0" y1="105" x2="400" y2="105" stroke="#f3f4f6" strokeWidth="1" />
                    {/* Y-axis labels */}
                    <text x="4" y="33" fontSize="8" fill="#9ca3af">₹11L</text>
                    <text x="4" y="68" fontSize="8" fill="#9ca3af">₹9.5L</text>
                    <text x="4" y="103" fontSize="8" fill="#9ca3af">₹8L</text>
                    {/* X-axis labels */}
                    <text x="28" y="130" fontSize="8" fill="#9ca3af">Jan</text>
                    <text x="90" y="130" fontSize="8" fill="#9ca3af">Feb</text>
                    <text x="152" y="130" fontSize="8" fill="#9ca3af">Mar</text>
                    <text x="210" y="130" fontSize="8" fill="#9ca3af">Apr</text>
                    <text x="272" y="130" fontSize="8" fill="#9ca3af">May</text>
                    <text x="340" y="130" fontSize="8" fill="#9ca3af">Jun</text>
                    {/* Area fill */}
                    <path d="M 30 105 L 90 92 L 150 100 L 210 72 L 270 58 L 360 28 L 360 120 L 30 120 Z" fill="url(#areaGrad)" />
                    {/* Line — animated draw */}
                    <path className="animate-draw" d="M 30 105 L 90 92 L 150 100 L 210 72 L 270 58 L 360 28" fill="none" stroke="#2563eb" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                    {/* Data points */}
                    <circle cx="30" cy="105" r="3.5" fill="#2563eb" stroke="#fff" strokeWidth="1.5" />
                    <circle cx="90" cy="92" r="3.5" fill="#2563eb" stroke="#fff" strokeWidth="1.5" />
                    <circle cx="150" cy="100" r="3.5" fill="#2563eb" stroke="#fff" strokeWidth="1.5" />
                    <circle cx="210" cy="72" r="3.5" fill="#2563eb" stroke="#fff" strokeWidth="1.5" />
                    <circle cx="270" cy="58" r="3.5" fill="#2563eb" stroke="#fff" strokeWidth="1.5" />
                    <circle cx="360" cy="28" r="4.5" fill="#2563eb" stroke="#fff" strokeWidth="2" />
                  </svg>
                  {/* Floating Tooltip */}
                  <div className="absolute top-3 right-6 bg-gray-900 text-white text-[9px] px-2 py-1 rounded shadow-lg leading-tight">
                    <div className="font-bold text-blue-300">June 2026</div>
                    <div>₹10,54,920</div>
                  </div>
                </div>
              </div>

              {/* Asset Allocation */}
              <div className="min-h-60 bg-white p-5 rounded-lg border border-gray-200 shadow-sm">
                <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider flex items-center gap-1.5 mb-3">
                  <PieChartIcon className="w-3.5 h-3.5 text-blue-600" /> Asset Allocation
                </h3>
                <div className="flex flex-col items-center justify-center gap-5 py-4 sm:h-[175px] sm:flex-row sm:gap-10 sm:py-0">
                  {/* Donut Chart */}
                  <div className="relative w-28 h-28 shrink-0">
                    <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                      <circle cx="18" cy="18" r="15.9155" fill="none" stroke="#e5e7eb" strokeWidth="3.5" />
                      <circle className="animate-donut" cx="18" cy="18" r="15.9155" fill="none" stroke="#2563eb" strokeWidth="3.5"
                        strokeDasharray="57 43" strokeDashoffset="0" />
                      <circle className="animate-donut" cx="18" cy="18" r="15.9155" fill="none" stroke="#60a5fa" strokeWidth="3.5"
                        strokeDasharray="27 73" strokeDashoffset="-57" style={{ animationDelay: "1.4s" }} />
                      <circle className="animate-donut" cx="18" cy="18" r="15.9155" fill="none" stroke="#1d4ed8" strokeWidth="3.5"
                        strokeDasharray="16 84" strokeDashoffset="-84" style={{ animationDelay: "1.6s" }} />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className="text-[8px] text-gray-400 font-bold uppercase">NSE</span>
                      <span className="text-xs font-extrabold text-gray-800">3 Stocks</span>
                    </div>
                  </div>
                  {/* Legend */}
                  <div className="space-y-3 text-xs">
                    {[
                      { color: "#2563eb", name: "RELIANCE.NS", pct: "57%" },
                      { color: "#60a5fa", name: "TCS.NS", pct: "27%" },
                      { color: "#1d4ed8", name: "HDFCBANK.NS", pct: "16%" },
                    ].map((item) => (
                      <div key={item.name} className="flex items-center gap-2.5">
                        <div className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: item.color }} />
                        <span className="font-semibold text-gray-700">{item.name}</span>
                        <span className="ml-auto text-gray-400 font-bold pl-4">{item.pct}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ─── Features Section — scroll-revealed ─── */}
        <section className="mt-32 w-full">
          <Reveal>
            <div className="text-center max-w-2xl mx-auto mb-14">
              <h2 className="text-3xl font-extrabold text-gray-900 tracking-tight">
                Built on Quantitative Fundamentals
              </h2>
              <p className="text-gray-500 mt-3 text-base leading-relaxed">
                Every number FinTrace shows you is derived from first principles — not estimates.
              </p>
            </div>
          </Reveal>

          <div className="grid md:grid-cols-3 gap-6">
            {/* Feature 1: XIRR — PRIMARY */}
            <Reveal delay={100}>
              <div className="relative bg-blue-600 text-white p-8 rounded-xl border border-blue-700 shadow-lg shadow-blue-500/20 flex flex-col gap-4 h-full hover:scale-[1.02] transition-transform duration-200">
                <div className="absolute top-4 right-4 text-[10px] font-bold bg-white/20 text-white px-2 py-0.5 rounded-full">
                  Core Feature
                </div>
                <div className="w-12 h-12 rounded-lg bg-white/20 flex items-center justify-center">
                  <Calculator className="w-6 h-6 text-white" />
                </div>
                <h3 className="text-lg font-bold">XIRR · Exact Returns</h3>
                <p className="text-sm text-blue-100 leading-relaxed">
                  Returns are calculated at the transaction level using a proper Internal Rate of Return (XIRR) formula — powered by <code className="font-mono bg-white/10 px-1 rounded">pyxirr</code>. Not a simple percentage estimate.
                </p>
              </div>
            </Reveal>

            {/* Feature 2: Immutable Ledger */}
            <Reveal delay={200}>
              <div className="bg-white p-8 rounded-xl border border-gray-200 shadow-sm hover:shadow-md hover:border-blue-200 hover:scale-[1.02] transition-all duration-200 flex flex-col gap-4 h-full">
                <div className="w-12 h-12 rounded-lg bg-blue-50 flex items-center justify-center text-blue-600">
                  <ShieldCheck className="w-6 h-6" />
                </div>
                <h3 className="text-lg font-bold text-gray-900">Immutable Ledger</h3>
                <p className="text-sm text-gray-500 leading-relaxed">
                  Every BUY, SELL, and DIVIDEND is stored in an append-only transaction ledger. Records are checksum-verified — they can never be silently altered, giving you a permanent audit trail.
                </p>
              </div>
            </Reveal>

            {/* Feature 3: FIFO Tax */}
            <Reveal delay={300}>
              <div className="bg-white p-8 rounded-xl border border-gray-200 shadow-sm hover:shadow-md hover:border-blue-200 hover:scale-[1.02] transition-all duration-200 flex flex-col gap-4 h-full">
                <div className="w-12 h-12 rounded-lg bg-blue-50 flex items-center justify-center text-blue-600">
                  <FileText className="w-6 h-6" />
                </div>
                <h3 className="text-lg font-bold text-gray-900">FIFO Tax Automation</h3>
                <p className="text-sm text-gray-500 leading-relaxed">
                  FinTrace maps settlement dates to execution dates to automatically classify your gains as Short-Term (STCG) or Long-Term (LTCG) under Indian tax law — and generates a downloadable PDF report.
                </p>
              </div>
            </Reveal>
          </div>
        </section>

        {/* ─── Final CTA Banner — scroll-revealed ─── */}
        <Reveal className="mt-24 w-full">
          <section>
            <div className="bg-gradient-to-br from-blue-600 to-indigo-700 rounded-2xl p-12 text-center text-white shadow-2xl shadow-blue-500/20 relative overflow-hidden">
              <div className="absolute inset-0 opacity-10" style={{ backgroundImage: 'radial-gradient(circle at 20% 50%, white 1px, transparent 1px)', backgroundSize: '24px 24px' }} />
              <h2 className="text-3xl font-extrabold mb-3 relative z-10">
                Know your real returns today.
              </h2>
              <p className="text-blue-100 text-lg mb-8 max-w-xl mx-auto relative z-10">
                Open registration. Upload your broker CSV and get your XIRR calculated in seconds.
              </p>
              <Link
                href="/register"
                className="inline-flex items-center gap-2 bg-white text-blue-700 font-bold px-8 py-4 rounded-lg hover:bg-blue-50 shadow-lg text-base group relative z-10 hover:scale-105 transition-all duration-200"
              >
                Create Your Free Account
                <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </Link>
            </div>
          </section>
        </Reveal>
      </main>

      {/* ─── Footer ─── */}
      <footer className="border-t border-gray-200 bg-white py-10 relative z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-gray-500">
          <div className="flex items-center space-x-2 font-bold text-gray-700">
            <Activity className="w-4 h-4 text-blue-600" />
            <span>FinTrace Engine</span>
          </div>
          <p>© {new Date().getFullYear()} FinTrace Engine. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
