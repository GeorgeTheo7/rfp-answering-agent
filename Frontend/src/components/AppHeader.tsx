import { useState, useEffect } from "react";
import { Moon, Sun, Key } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

export function AppHeader() {
  // --- DARK MODE LOGIC ---
  const [isDark, setIsDark] = useState(false);

  // --- SECRETS LOGIC (UI state only for now) ---
  const [openAiKey, setOpenAiKey] = useState("");
  const [llamaKey, setLlamaKey] = useState("");

  // Check whether the site is already in dark mode on load
  useEffect(() => {
    if (document.documentElement.classList.contains("dark")) {
      setIsDark(true);
    }
  }, []);

  // Toggles the theme
  const toggleTheme = (e: React.MouseEvent) => {
    e.preventDefault();

    if (isDark) {
      document.documentElement.classList.remove("dark");
      setIsDark(false);
    } else {
      document.documentElement.classList.add("dark");
      setIsDark(true);
    }
  };

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-surface/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        {/* --- LOGO (LEFT) --- */}
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-soft">
            <span className="text-lg font-extrabold tracking-tighter">R</span>
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-[15px] font-semibold tracking-tight text-foreground">
              RFP AGENT
            </span>
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              LogistiComp
            </span>
          </div>
        </div>

        {/* --- MENU (RIGHT) --- */}
        <div className="flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-2 rounded-full p-1 transition-colors hover:bg-accent">
                <Avatar className="h-8 w-8 border border-border">
                  <AvatarFallback className="bg-primary/10 text-xs font-semibold text-primary">
                    LC
                  </AvatarFallback>
                </Avatar>
              </button>
            </DropdownMenuTrigger>

            {/* Width w-72 so the inputs fit comfortably */}
            <DropdownMenuContent align="end" className="w-72">
              <DropdownMenuLabel>
                <div className="flex items-center justify-between py-1">
                  {/* Avatar and name */}
                  <div className="flex items-center gap-3">
                    <Avatar className="h-8 w-8 border border-border">
                      <AvatarFallback className="bg-primary/10 text-xs font-semibold text-primary">
                        LC
                      </AvatarFallback>
                    </Avatar>
                    <span className="text-sm font-semibold">LogistiComp</span>
                  </div>

                  {/* Dark mode button */}
                  <button
                    onClick={toggleTheme}
                    className="flex h-8 w-8 items-center justify-center rounded-full hover:bg-accent hover:text-accent-foreground transition-colors"
                    title="Toggle theme"
                  >
                    {isDark ? (
                      <Sun className="h-4 w-4 text-orange-400" />
                    ) : (
                      <Moon className="h-4 w-4 text-slate-500" />
                    )}
                  </button>
                </div>
              </DropdownMenuLabel>

              {/* Divider */}
              <div className="h-px bg-border my-1" />

              {/* --- SECRETS SECTION --- */}
              <div className="px-3 py-3">
                <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  <Key className="h-3.5 w-3.5" />
                  API Secrets
                </div>

                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-foreground">OpenAI API Key</label>
                    <input
                      type="password"
                      value={openAiKey}
                      onChange={(e) => setOpenAiKey(e.target.value)}
                      // stopPropagation keeps the menu open when clicking the input
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => e.stopPropagation()}
                      placeholder="sk-proj-..."
                      className="w-full h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary transition-shadow"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-foreground">
                      LlamaParse API Key
                    </label>
                    <input
                      type="password"
                      value={llamaKey}
                      onChange={(e) => setLlamaKey(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => e.stopPropagation()}
                      placeholder="llx-..."
                      className="w-full h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary transition-shadow"
                    />
                  </div>
                </div>
              </div>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
