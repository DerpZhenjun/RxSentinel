/** 情报流虚拟列表：按行估算高度与前缀偏移，供滚动定位与窗口切片共用 */

export const ROW_GAP = 15;
const ROW_BASE = 172;
const LINE_PX = 17;

const _hasUrl = (url) => {
  const text = String(url || '').trim();
  return text.startsWith('http://') || text.startsWith('https://');
};

/** 与 IntelligenceFeed 卡片 DOM 结构对齐的估算高度（含 margin-bottom） */
export function estimateRowHeight(item) {
  let h = ROW_BASE;
  if (item.threadParent) {
    h += 48 + Math.min(88, Math.ceil(String(item.threadParent).length / 26) * LINE_PX);
  } else if (item.replyTargetNick) {
    h += 36;
  }
  h += Math.min(80, Math.ceil(String(item.content || '').length / 30) * LINE_PX);
  h += Math.min(64, Math.ceil(String(item.analysis || '').length / 34) * LINE_PX);
  if (_hasUrl(item.source_url)) h += 26;
  return Math.max(228, h) + ROW_GAP;
}

export function buildRowMetrics(items) {
  const heights = items.map(estimateRowHeight);
  const offsets = new Array(heights.length + 1);
  offsets[0] = 0;
  for (let i = 0; i < heights.length; i++) {
    offsets[i + 1] = offsets[i] + heights[i];
  }
  return { heights, offsets, total: offsets[heights.length] || 0 };
}

/** 最大 i 满足 offsets[i] <= y */
export function findIndexAtOffset(offsets, y) {
  const n = offsets.length - 1;
  if (n <= 0) return 0;
  let lo = 0;
  let hi = n - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (offsets[mid] <= y) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

export function scrollTopToCenterIndex(offsets, heights, index, viewportH) {
  const rowTop = offsets[index] ?? 0;
  const h = heights[index] ?? 260;
  return Math.max(0, rowTop - viewportH / 2 + h / 2);
}
