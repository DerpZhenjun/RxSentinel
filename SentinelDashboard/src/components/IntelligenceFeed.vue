<template>
  <div class="feed-container">
    <div class="header-banner">
      <span class="pulse-dot"></span> 核心情报流转区 (实时侦测)
      <span v-if="store.dataMode === 'jsonl'" class="mode-badge mode-offline">⚠ 离线模式</span>
      <span v-else-if="store.dataMode === 'error'" class="mode-badge mode-error">✕ 数据异常</span>
    </div>

    <div class="scroll-area" ref="scrollAreaRef" @scroll="handleScroll">
      <div class="virtual-spacer" :style="{ height: `${totalHeight}px` }">
        <div
          class="virtual-window"
          :style="{ transform: `translateY(${translateY}px)` }"
        >
          <div
            v-for="row in visibleRows"
            :key="row.index"
            :id="`feed-item-${row.index}`"
            class="feed-card"
            :class="{
              'high-risk': row.item.merchant !== '无' && row.item.merchant !== '未指明',
              'flash-target': flashIndex === row.index
            }"
          >
            <div class="card-header">
              <div class="source-tag" :class="row.item.platformType">[{{ row.item.platform }}]</div>
              <div class="entity-name" v-if="row.item.merchant !== '无' && row.item.merchant !== '未指明'">
                实体：{{ row.item.merchant }}
              </div>
              <div class="entity-name safe" v-else>实体: 无</div>

              <div
                class="source-title-block"
                v-if="isValidUrl(row.item.source_url)"
              >
                <span class="field-label">来源标题</span>
                <a
                  class="source-link"
                  :href="row.item.source_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  title="落地链接：在浏览器中打开该作品/笔记的原始页面（与标题文案无关）"
                >
                  🔗 {{ formatTitle(row.item.video_title) }}
                </a>
                <span
                  v-if="store.urlAliveness[row.item.source_url] === 'dead'"
                  class="source-warn source-warn-dead"
                  title="服务端判定：该落地页已失效或疑似被平台删除"
                >⚠</span>
              </div>
            </div>

            <div class="card-content">"{{ row.item.content }}"</div>
            <div class="card-analysis">
              <span class="ai-icon">🤖 AI 研判:</span> {{ row.item.analysis }}
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
 * 定高虚拟列表：`slice` + `translateY`，DOM 只押可见窗口。
 * `watchEffect` 对可见行 enqueue 探活；触底调 `loadMoreData`。
 * `scrollTrigger`：榜单点击 → 平滑滚动 + `flash-target` 锚定闪烁。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue';
import { useSentinelStore } from '../stores/sentinelStore';

const store = useSentinelStore();
const flashIndex = ref(-1);
const scrollAreaRef = ref(null);
const scrollTop = ref(0);
const viewportHeight = ref(0);

const ITEM_HEIGHT = 164;
const OVERSCAN = 6;

const totalHeight = computed(() => store.intelData.length * ITEM_HEIGHT);
const visibleCount = computed(() => Math.max(1, Math.ceil((viewportHeight.value || 0) / ITEM_HEIGHT) + OVERSCAN * 2));
const startIndex = computed(() => Math.max(0, Math.floor((scrollTop.value || 0) / ITEM_HEIGHT) - OVERSCAN));
const endIndex = computed(() => Math.min(store.intelData.length, startIndex.value + visibleCount.value));
const translateY = computed(() => startIndex.value * ITEM_HEIGHT);
const visibleRows = computed(() =>
  store.intelData.slice(startIndex.value, endIndex.value).map((item, offset) => ({
    item,
    index: startIndex.value + offset
  }))
);

const refreshViewportSize = () => {
  const el = scrollAreaRef.value;
  if (!el) return;
  viewportHeight.value = el.clientHeight;
};

/** 展示用作品标题；无管线字段时统一占位，不把 BV/av/路径误当作「标题」。 */
const formatTitle = (title) => {
  const t = String(title || '').trim();
  if (!t) return '标题未收录';
  return t.length > 20 ? t.substring(0, 20) + '...' : t;
};

/** 拦 Markdown 半成品链、无路径号的 `/video/`，禁止 `<a>` 误跳 */
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

watch(() => store.scrollTrigger, () => {
  const targetIndex = store.activeIntelIndex;
  if (targetIndex < 0) return;

  const el = scrollAreaRef.value;
  if (el) {
    const targetTop = Math.max(0, targetIndex * ITEM_HEIGHT - el.clientHeight / 2 + ITEM_HEIGHT / 2);
    if (typeof el.scrollTo === 'function') {
      el.scrollTo({ top: targetTop, behavior: 'smooth' });
    } else {
      el.scrollTop = targetTop;
    }
    scrollTop.value = targetTop;
    refreshViewportSize();

    flashIndex.value = targetIndex;
    setTimeout(() => { flashIndex.value = -1; }, 2500);
  }
});

watch(
  () => store.intelData.length,
  () => {
    refreshViewportSize();
    const maxTop = Math.max(0, totalHeight.value - viewportHeight.value);
    if (scrollTop.value > maxTop) scrollTop.value = maxTop;
  },
  { immediate: true }
);

watchEffect(() => {
  visibleRows.value.forEach(row => {
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

.scroll-area { flex: 1; overflow-y: auto; padding-right: 10px; scroll-behavior: smooth; }
.scroll-area::-webkit-scrollbar { width: 4px; }
.scroll-area::-webkit-scrollbar-thumb { background: rgba(0, 186, 255, 0.5); border-radius: 2px; }
.virtual-spacer { position: relative; width: 100%; }
.virtual-window { position: absolute; top: 0; left: 0; width: 100%; will-change: transform; }

.feed-card { position: relative; overflow: hidden; background: rgba(0, 186, 255, 0.07); border: 1px solid rgba(0, 186, 255, 0.24); border-left: 3px solid #00baff; border-radius: 6px; padding: 12px; margin-bottom: 15px; min-height: 149px; box-sizing: border-box; transition: all 0.3s; }
.feed-card::before { content: ''; position: absolute; inset: 0; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.08), transparent); transform: translateX(-130%); transition: transform 0.45s ease; }
.feed-card:hover { background: rgba(0, 186, 255, 0.14); transform: translateX(4px); box-shadow: 0 0 14px rgba(0, 186, 255, 0.25); }
.feed-card:hover::before { transform: translateX(120%); }

.feed-card.high-risk { border-left-color: #ff4d4f; background: rgba(255, 77, 79, 0.08); }

.feed-card.flash-target {
  animation: flash-border 2.5s ease-out;
  background: rgba(255, 77, 79, 0.15);
}
@keyframes flash-border {
  0% { box-shadow: 0 0 0px #ff4d4f; border-color: #ff4d4f; }
  20% { box-shadow: 0 0 20px #ff4d4f; border-color: #fff; }
  40% { box-shadow: 0 0 0px #ff4d4f; border-color: #ff4d4f; }
  60% { box-shadow: 0 0 20px #ff4d4f; border-color: #fff; }
  100% { box-shadow: 0 0 0px transparent; border-color: #ff4d4f; }
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
.card-content { font-size: 14px; line-height: 1.6; color: #d8eeff; font-style: italic; margin-bottom: 10px; background: rgba(0,0,0,0.28); padding: 8px; border-radius: 4px; }
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
