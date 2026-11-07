import { useState, useCallback, type DragEvent } from "react";
import { UploadCloud, FileText, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DropZoneProps {
  title: string;
  subtitle?: string;
  accept?: string;
  files: File[];
  onFilesChange: (files: File[]) => void;
}

export function DropZone({ title, subtitle, accept, files, onFilesChange }: DropZoneProps) {
  const [isOver, setIsOver] = useState(false);

  const handleDrop = useCallback(
    (e: DragEvent<HTMLLabelElement>) => {
      e.preventDefault();
      setIsOver(false);
      const dropped = Array.from(e.dataTransfer.files);
      onFilesChange([...files, ...dropped]);
    },
    [files, onFilesChange],
  );

  const removeFile = (idx: number) => {
    onFilesChange(files.filter((_, i) => i !== idx));
  };

  return (
    <div className="space-y-3">
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setIsOver(true);
        }}
        onDragLeave={() => setIsOver(false)}
        onDrop={handleDrop}
        className={cn(
          "group relative flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed bg-surface p-10 text-center transition-all duration-200",
          isOver
            ? "border-primary bg-primary/5 shadow-glow"
            : "border-border hover:border-primary/50 hover:bg-accent/40",
        )}
      >
        <input
          type="file"
          multiple
          accept={accept}
          className="sr-only"
          onChange={(e) => {
            if (e.target.files) onFilesChange([...files, ...Array.from(e.target.files)]);
          }}
        />
        <div
          className={cn(
            "mb-4 flex h-14 w-14 items-center justify-center rounded-full transition-all",
            isOver ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary",
          )}
        >
          <UploadCloud className="h-7 w-7" />
        </div>
        <p className="text-base font-semibold text-foreground">{title}</p>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
        <p className="mt-3 text-xs text-muted-foreground">
          or <span className="font-medium text-primary">browse files</span>
        </p>
      </label>

      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2 text-sm shadow-soft"
            >
              <div className="flex items-center gap-2 truncate">
                <FileText className="h-4 w-4 shrink-0 text-primary" />
                <span className="truncate font-medium text-foreground">{f.name}</span>
                <span className="text-xs text-muted-foreground">
                  {(f.size / 1024).toFixed(1)} KB
                </span>
              </div>
              <button
                onClick={() => removeFile(i)}
                className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                aria-label="Remove file"
              >
                <X className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
