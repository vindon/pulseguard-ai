type CategoryTone = 'violet' | 'teal' | 'rose';

const TONE_CLASSES: Record<CategoryTone, string> = {
  violet: 'bg-jewel-violet-tint text-jewel-violet',
  teal: 'bg-jewel-teal-tint text-jewel-teal',
  rose: 'bg-jewel-rose-tint text-jewel-rose',
};

const TONES: CategoryTone[] = ['violet', 'teal', 'rose'];

// Deterministic hash so the same category string always renders the same
// jewel tone across the app, without maintaining a manual category-to-color
// map that would need updating every time Triage introduces a new category.
export function categoryTone(category: string): CategoryTone {
  let hash = 0;
  for (let i = 0; i < category.length; i++) {
    hash = (hash * 31 + category.charCodeAt(i)) >>> 0;
  }
  return TONES[hash % TONES.length];
}

export default function CategoryChip({ category }: { category: string }) {
  const tone = categoryTone(category);
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full px-[7px] py-0.5 text-[9.5px] font-bold ${TONE_CLASSES[tone]}`}
    >
      {category}
    </span>
  );
}
