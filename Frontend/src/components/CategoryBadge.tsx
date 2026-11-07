import { cn } from "@/lib/utils";

export type Category = "Security" | "Tech" | "Product" | "Legal";

const styles: Record<Category, string> = {
  Security: "bg-cat-security text-cat-security-fg ring-cat-security-fg/20",
  Tech: "bg-cat-tech text-cat-tech-fg ring-cat-tech-fg/20",
  Product: "bg-cat-product text-cat-product-fg ring-cat-product-fg/20",
  Legal: "bg-cat-legal text-cat-legal-fg ring-cat-legal-fg/20",
};

export function CategoryBadge({ category }: { category: Category }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        styles[category],
      )}
    >
      {category}
    </span>
  );
}
