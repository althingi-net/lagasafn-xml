interface LawStatsProps {
  totalCount: number;
  emptyCount: number;
  nonEmptyCount: number;
}

export default function LawStats(props: LawStatsProps) {
  return (
    <div class="mt-8 mb-4 flex justify-between text-sm">
      <span><b>Total law count:</b> {props.totalCount}</span>
      <span><b>Empty law count:</b> {props.emptyCount}</span>
      <span><b>Non-empty law count:</b> {props.nonEmptyCount}</span>
    </div>
  );
} 