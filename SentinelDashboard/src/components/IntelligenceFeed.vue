<template>
  <div class="feed-container">
    <div class="header-banner">
      <span class="pulse-dot"></span> 核心情报流转区 (实时侦测)
      <span v-if="store.dataMode === 'jsonl'" class="mode-badge mode-offline">⚠ 离线模式</span>
      <span v-else-if="store.dataMode === 'error'" class="mode-badge mode-error">✕ 数据异常</span>
    </div>

    <div
      class="scroll-area"
      ref="scrollAreaRef"
      :class="{ 'scroll-area--programmatic': programmaticScroll }"
      @scroll="handleScroll"
    >
      <!-- 小数据量：全量渲染，滚动定位最稳（验证集约 70 条） -->
      <template v-if="useFullList">
        <div
          v-for="(item, index) in store.intelData"
          :key="item.leadKey || index"
          class="feed-row-slot"
        >
          <div
            :id="`feed-item-${index}`"
            class="feed-card"
            :class="cardClass(item, index)"
          >
            <FocusTargetBadge v-if="store.activeIntelIndex === index" />
            <FeedCardBody :item="item" :format-title="formatTitle" :is-valid-url="isValidUrl" />
          </div>
        </div>
      </template>

      <!-- 大数据量：可变行高虚拟列表 -->
      <div v-else class="virtual-spacer" :style="{ height: `${rowMetrics.total}px` }">
        <div
          class="virtual-window"
          :style="{ transform: `translateY(${translateY}px)` }"
        >
          <div
            v-for="row in visibleRows"
            :key="row.item.leadKey || row.index"
            class="feed-row-slot"
            :style="{ height: `${row.height}px` }"
          >
          <div
            :id="`feed-item-${row.index}`"
            class="feed-card feed-card--in-slot"
            :class="cardClass(row.item, row.index)"
          >
            <FocusTargetBadge v-if="store.activeIntelIndex === row.index" />
            <FeedCardBody :item="row.item" :format-title="formatTitle" :is-valid-url="isValidUrl" />
          </div>
          </div>
        </div>
      </div>
    </div>
    <div class="load-more-status" v-if="store.useMongoApi">
      <span v-if="store.isLoadingMore">加载更多中...</span>
      <span v-else-if="store.hasNextPage">下滑加载更多</span>
      <span v-else>已加载全部数据</span>
    </div>
  </div>
</template>

<script setup>
/**
 * 可变行高虚拟列表 + 小数据全量渲染；榜单点击用前缀偏移滚动居中。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue';
import { useSentinelStore } from '../stores/sentinelStore';
import FeedCardBody from './FeedCardBody.vue';
import FocusTargetBadge from './FocusTargetBadge.vue';
import {
  buildRowMetrics,
  findIndexAtOffset,
  scrollTopToCenterIndex,
} from './feedRowMetrics.js';

const FULL_LIST_THRESHOLD = 150;
const OVERSCAN = 4;
const AVG_ROW = 268;

const store = useSentinelStore();
const focusPopIndex = ref(-1);
let focusPopTimer = null;
const scrollAreaRef = ref(null);
const scrollTop = ref(0);
const viewportHeight = ref(0);
const programmaticScroll = ref(false);
let scrollJobGen = 0;

const useFullList = computed(() => store.intelData.length <= FULL_LIST_THRESHOLD);

const rowMetrics = computed(() => buildRowMetrics(store.intelData));

const startIndex = computed(() => {
  if (useFullList.value) return 0;
  const { offsets } = rowMetrics.value;
  const n = store.intelData.length;
  if (!n) return 0;
  const cushion = OVERSCAN * AVG_ROW;
  return Math.max(0, findIndexAtOffset(offsets, Math.max(0, scrollTop.value - cushion)));
});

const endIndex = computed(() => {
  if (useFullList.value) return store.intelData.length;
  const { offsets } = rowMetrics.value;
  const n = store.intelData.length;
  if (!n) return 0;
  const viewBottom = scrollTop.value + (viewportHeight.value || 600) + OVERSCAN * AVG_ROW;
  const last = findIndexAtOffset(offsets, viewBottom);
  return Math.min(n, last + 1 + OVERSCAN);
});

const translateY = computed(() => {
  if (useFullList.value) return 0;
  return rowMetrics.value.offsets[startIndex.value] || 0;
});

const visibleRows = computed(() => {
  const { heights } = rowMetrics.value;
  return store.intelData.slice(startIndex.value, endIndex.value).map((item, offset) => {
    const index = startIndex.value + offset;
    return { item, index, height: heights[index] ?? AVG_ROW };
  });
});

const cardClass = (item, index) => ({
  'high-risk': item.merchant !== '无' && item.merchant !== '未指明',
  'is-focused': store.activeIntelIndex === index,
  'focus-pop': focusPopIndex.value === index,
});

const refreshViewportSize = () => {
  const el = scrollAreaRef.value;
  if (!el) return;
  viewportHeight.value = el.clientHeight;
};

const formatTitle = (title) => {
  const t = String(title || '').trim();
  if (!t) return '标题未收录';
  return t.length > 20 ? t.substring(0, 20) + '...' : t;
};

const isValidUrl = (url) => {
  if (!url) return false;
  const text = String(url).trim();
  if (!text.startsWith('http://') && !text.startsWith('https://')) return false;
  if (text.includes('](')) return false;
  if (text.endsWith('/video/av') || text.endsWith('/video/')) return false;
  return true;
};

const handleScroll = () => {
  const el = scrollAreaRef.value;
  if (!el) return;
  scrollTop.value = el.scrollTop;
  refreshViewportSize();
  if (!store.useMongoApi || store.isLoadingMore || !store.hasNextPage) return;
  const reachBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 80;
  if (reachBottom) store.loadMoreData();
};

const centerCardInViewport = (el, node) => {
  const cRect = el.getBoundingClientRect();
  const nRect = node.getBoundingClientRect();
  const delta = nRect.top - cRect.top - el.clientHeight / 2 + nRect.height / 2;
  el.scrollTop = Math.max(0, el.scrollTop + delta);
  scrollTop.value = el.scrollTop;
};

/** 榜单跳转：串行 job + 重试直至目标行挂载（不用 scrollIntoView） */
const scrollToIntelIndex = async (targetIndex) => {
  const el = scrollAreaRef.value;
  if (!el || targetIndex < 0 || targetIndex >= store.intelData.length) return;

  const job = ++scrollJobGen;
  programmaticScroll.value = true;

  try {
    for (let attempt = 0; attempt < 8 && job === scrollJobGen; attempt++) {
      refreshViewportSize();
      const vh = el.clientHeight || viewportHeight.value;

      if (useFullList.value) {
        await nextTick();
        const node = document.getElementById(`feed-item-${targetIndex}`);
        if (node) {
          centerCardInViewport(el, node);
          return;
        }
      } else {
        const { offsets, heights } = rowMetrics.value;
        const top = scrollTopToCenterIndex(offsets, heights, targetIndex, vh);
        scrollTop.value = top;
        await nextTick();
        el.scrollTop = top;
        scrollTop.value = el.scrollTop;
        await nextTick();
        const node = document.getElementById(`feed-item-${targetIndex}`);
        if (node) {
          centerCardInViewport(el, node);
          scrollTop.value = el.scrollTop;
          return;
        }
      }
      await new Promise((r) => setTimeout(r, 40));
    }
  } finally {
    if (job === scrollJobGen) programmaticScroll.value = false;
  }
};

watch(() => store.scrollTrigger, async () => {
  const targetIndex = store.activeIntelIndex;
  if (targetIndex < 0) return;

  focusPopIndex.value = targetIndex;
  if (focusPopTimer) clearTimeout(focusPopTimer);
  focusPopTimer = setTimeout(() => {
    focusPopIndex.value = -1;
    focusPopTimer = null;
  }, 900);

  await scrollToIntelIndex(targetIndex);
});

watch(
  () => store.intelData.length,
  () => {
    refreshViewportSize();
    const maxTop = Math.max(0, rowMetrics.value.total - viewportHeight.value);
    if (scrollTop.value > maxTop) scrollTop.value = maxTop;
  },
  { immediate: true }
);

watchEffect(() => {
  const rows = useFullList.value
    ? store.intelData.map((item, index) => ({ item, index }))
    : visibleRows.value;
  rows.forEach((row) => {
    const url = row.item.source_url;
    if (url) store.checkUrlAliveness(url);
  });
});

onMounted(() => {
  refreshViewportSize();
  window.addEventListener('resize', refreshViewportSize);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', refreshViewportSize);
  if (focusPopTimer) clearTimeout(focusPopTimer);
  scrollJobGen++;
});
</script>

<style scoped>
.feed-container { width: 100%; height: 100%; display: flex; flex-direction: column; padding: 15px; box-sizing: border-box; }
.header-banner { font-size: 18px; font-weight: bold; color: #00e5ff; margin-bottom: 15px; display: flex; align-items: center; justify-content: center; gap: 10px; text-shadow: 0 0 8px rgba(0, 229, 255, 0.45); }
.mode-badge { font-size: 11px; font-weight: bold; padding: 2px 8px; border-radius: 3px; letter-spacing: 0.5px; }
.mode-offline { background: rgba(250,173,20,0.18); color: #faad14; border: 1px solid #faad14; }
.mode-error { background: rgba(255,77,79,0.18); color: #ff4d4f; border: 1px solid #ff4d4f; }
.pulse-dot { width: 10px; height: 10px; background-color: #ff4d4f; border-radius: 50%; margin-right: 10px; animation: pulse 1.5s infinite; }
@keyframes pulse { 0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 77, 79, 0.7); } 70% { transform: scale(1.2); box-shadow: 0 0 0 6px rgba(255, 77, 79, 0); } 100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 77, 79, 0); } }

.scroll-area { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 8px 10px 8px 4px; scroll-behavior: smooth; }
.scroll-area--programmatic { scroll-behavior: auto; }
.feed-row-slot { position: relative; width: 100%; box-sizing: border-box; }
.feed-card--in-slot { margin-bottom: 0; min-height: 0; height: calc(100% - 2px); }
.scroll-area::-webkit-scrollbar { width: 4px; }
.scroll-area::-webkit-scrollbar-thumb { background: rgba(0, 186, 255, 0.5); border-radius: 2px; }
.virtual-spacer { position: relative; width: 100%; }
.virtual-window { position: absolute; top: 0; left: 0; width: 100%; will-change: transform; }

.feed-card {
  position: relative;
  overflow: visible;
  background: rgba(0, 186, 255, 0.07);
  border: 1px solid rgba(0, 186, 255, 0.24);
  border-left: 3px solid #00baff;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 15px;
  min-height: 149px;
  box-sizing: border-box;
  transition: background 0.35s ease, border-color 0.35s ease, box-shadow 0.35s ease, transform 0.35s ease;
}
.feed-card::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.08), transparent);
  transform: translateX(-130%);
  transition: transform 0.45s ease;
  pointer-events: none;
}
.feed-card:hover:not(.is-focused) {
  background: rgba(0, 186, 255, 0.14);
  transform: translateX(4px);
  box-shadow: 0 0 14px rgba(0, 186, 255, 0.25);
}
.feed-card:hover:not(.is-focused)::before { transform: translateX(120%); }

.feed-card.high-risk { border-left-color: #ff4d4f; background: rgba(255, 77, 79, 0.08); }

/* 右侧榜单点击后：持久锁定高亮（直到点击其他实体） */
.feed-card.is-focused {
  z-index: 8;
  transform: scale(1.045) translateX(8px);
  background: linear-gradient(125deg, rgba(0, 229, 255, 0.28) 0%, rgba(255, 77, 79, 0.14) 55%, rgba(0, 80, 120, 0.35) 100%);
  border: 2px solid #00e5ff;
  border-left: 5px solid #ffeb3b;
  box-shadow:
    0 0 0 1px rgba(255, 235, 59, 0.45),
    0 0 24px rgba(0, 229, 255, 0.55),
    0 0 40px rgba(255, 77, 79, 0.28);
  animation: focus-hold-pulse 2.2s ease-in-out infinite;
}
.feed-card.is-focused.high-risk {
  border-left-color: #ffeb3b;
  background: linear-gradient(125deg, rgba(255, 77, 79, 0.22) 0%, rgba(0, 229, 255, 0.18) 100%);
}
.feed-card.is-focused:hover {
  transform: scale(1.05) translateX(8px);
}

.feed-card.focus-pop {
  animation: focus-pop-in 0.85s cubic-bezier(0.22, 1, 0.36, 1), focus-hold-pulse 2.2s ease-in-out 0.85s infinite;
}

@keyframes focus-pop-in {
  0% { transform: scale(0.92) translateX(0); opacity: 0.75; }
  45% { transform: scale(1.08) translateX(10px); opacity: 1; }
  100% { transform: scale(1.045) translateX(8px); opacity: 1; }
}

@keyframes focus-hold-pulse {
  0%, 100% {
    box-shadow:
      0 0 0 1px rgba(255, 235, 59, 0.4),
      0 0 20px rgba(0, 229, 255, 0.45),
      0 0 32px rgba(255, 77, 79, 0.2);
  }
  50% {
    box-shadow:
      0 0 0 2px rgba(255, 235, 59, 0.75),
      0 0 32px rgba(0, 229, 255, 0.75),
      0 0 48px rgba(255, 235, 59, 0.35);
  }
}

.card-header { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 10px; margin-bottom: 10px; font-size: 13px; }
.source-title-block { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 4px 8px; margin-left: auto; max-width: min(100%, 320px); justify-content: flex-end; }
.field-label { font-size: 11px; color: #6a9ec4; font-weight: normal; letter-spacing: 0.5px; flex-shrink: 0; }
.source-tag { padding: 2px 6px; border-radius: 3px; margin-right: 10px; font-weight: bold; }
.entity-name { background: rgba(255,77,79,0.2); color: #ff4d4f; border: 1px solid #ff4d4f; padding: 2px 8px; border-radius: 3px; font-weight: bold; }
.entity-name.safe { background: rgba(255,255,255,0.1); color: #aaa; border: 1px solid #555; }
.source-link { color: #8bbce6; text-decoration: none; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: color 0.2s; flex-shrink: 0; }
.source-link:hover { color: #00baff; text-decoration: underline; }
.source-warn { font-size: 0.75em; opacity: 0.9; margin-left: 3px; vertical-align: super; font-weight: bold; flex-shrink: 0; cursor: default; }
.source-warn-dead { color: #faad14; }
.card-content { font-size: 14px; line-height: 1.6; color: #d8eeff; margin-bottom: 10px; background: rgba(0,0,0,0.28); padding: 8px; border-radius: 4px; }
.thread-parent { font-size: 12px; color: #9ecfff; margin-bottom: 8px; font-style: normal; line-height: 1.45; word-break: break-word; }
.thread-parent-hint { color: #b8d9f0; }
.thread-parent-text { display: block; margin-top: 4px; white-space: pre-wrap; }
.thread-at { color: #69e0ff; font-weight: 600; }
.thread-hint-note { font-size: 11px; color: #7a9aad; margin-left: 4px; }
.thread-label { display: inline-block; margin-right: 6px; padding: 1px 6px; border-radius: 2px; background: rgba(0,186,255,0.15); color: #00e5ff; font-size: 11px; vertical-align: middle; }
.thread-self { font-style: italic; color: #d8eeff; }
.thread-self-label { display: inline-block; margin-right: 6px; font-size: 11px; font-style: normal; color: #6a9ec4; vertical-align: middle; }
.card-analysis { font-size: 13px; color: #ffd66f; line-height: 1.5; border-top: 1px dashed rgba(255,255,255,0.1); padding-top: 8px; }
.ai-icon { font-weight: bold; color: #ff7675; }

.tag-blue { background: rgba(0,186,255,0.2); color: #00baff; }
.tag-red { background: rgba(255,77,79,0.2); color: #ff4d4f; }
.tag-green { background: rgba(82,196,26,0.2); color: #52c41a; }
.tag-yellow { background: rgba(250,173,20,0.2); color: #faad14; }
.tag-cyan { background: rgba(19,194,194,0.2); color: #13c2c2; }
.tag-dark { background: rgba(200,200,200,0.2); color: #fff; }
.load-more-status { flex: 0 0 20px; font-size: 12px; color: #7eb9dd; text-align: center; margin-top: 6px; }
</style>
