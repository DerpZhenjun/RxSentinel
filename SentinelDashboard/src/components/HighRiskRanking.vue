<template>
  <div class="custom-ranking-board"
       @mouseenter="pauseScroll"
       @mouseleave="resumeScroll"
       ref="rankingBoardRef">

    <div v-if="store.rankingData.length === 0" class="loading">暂无明确实体目标...</div>

    <div v-for="(item, index) in store.rankingData" :key="index"
         class="ranking-item"
         :class="{ 'is-active': store.activeMerchant === item.name }"
         @click="handleItemClick(item)">
       <div class="rank-index" :class="index < 3 ? 'top-three' : ''">NO.{{ index + 1 }}</div>
       <div class="rank-info">
         <span class="rank-plat" :class="store.getTagColor(item.platform)">{{ item.platform }}</span>
         <span class="rank-name">{{ item.name }}</span>
       </div>
       <div class="rank-count">{{ item.value }} 次</div>
    </div>
  </div>
</template>

<script setup>
/**
 * 纵向跑马：定时 `scrollTop += 1`，触底归零循环。
 * 悬停 `pauseScroll`；点击调用 `focusMerchant` 驱动中流。
 */
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { useSentinelStore } from '../stores/sentinelStore';

const store = useSentinelStore();

const handleItemClick = (item) => {
  store.focusMerchant(item.name, item.platform);
};

const rankingBoardRef = ref(null);
let scrollInterval = null;
let isHovering = false;

const startScroll = () => {
  if (scrollInterval) clearInterval(scrollInterval);
  scrollInterval = setInterval(() => {
    if (rankingBoardRef.value && !isHovering) {
      rankingBoardRef.value.scrollTop += 1;
      if (rankingBoardRef.value.scrollTop >= rankingBoardRef.value.scrollHeight - rankingBoardRef.value.clientHeight) {
        rankingBoardRef.value.scrollTop = 0;
      }
    }
  }, 40);
};

const pauseScroll = () => { isHovering = true; };
const resumeScroll = () => { isHovering = false; };

watch(() => store.rankingData, () => {
  nextTick(() => {
    if (!scrollInterval) startScroll();
  });
}, { deep: true });

onMounted(() => {
  startScroll();
});

onUnmounted(() => {
  if (scrollInterval) clearInterval(scrollInterval);
});
</script>

<style scoped>
.custom-ranking-board { width: 100%; height: 100%; overflow-y: auto; padding-right: 5px; scroll-behavior: smooth; }
.custom-ranking-board::-webkit-scrollbar { display: none; }
.ranking-item {
  display: flex; align-items: center; justify-content: space-between;
  position: relative;
  overflow: hidden;
  background: rgba(0, 186, 255, 0.05); border: 1px solid rgba(0, 186, 255, 0.16);
  padding: 12px 10px; margin-bottom: 8px; border-radius: 6px; cursor: pointer; transition: all 0.3s ease;
}
.ranking-item::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.12), transparent);
  transform: translateX(-120%);
  transition: transform 0.4s ease;
}
.ranking-item:hover, .ranking-item.is-active {
  background: rgba(0, 186, 255, 0.17); border-color: #00d9ff; transform: translateX(4px);
  box-shadow: 0 0 14px rgba(0, 186, 255, 0.35);
}
.ranking-item:hover::before, .ranking-item.is-active::before {
  transform: translateX(120%);
}
.rank-index { font-family: Impact, sans-serif; font-size: 16px; color: #5a7f9e; width: 40px; }
.rank-index.top-three { color: #f4d03f; text-shadow: 0 0 8px rgba(244, 208, 63, 0.65); }
.rank-info { flex: 1; display: flex; align-items: center; gap: 8px; overflow: hidden; }
.rank-plat { font-size: 12px; padding: 2px 6px; border-radius: 3px; white-space: nowrap; }
.rank-name { font-size: 13px; color: #d0e4f5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rank-count { font-size: 16px; font-weight: bold; color: #ff5f66; width: 45px; text-align: right; text-shadow: 0 0 8px rgba(255, 95, 102, 0.45); }

.loading { text-align: center; color: #a0b2c6; animation: loading-pulse 2s infinite; margin-top: 60px; }
@keyframes loading-pulse { 0% { opacity: 0.5; } 50% { opacity: 1; } 100% { opacity: 0.5; } }

.tag-blue { background: rgba(0,186,255,0.2); color: #00baff; border: 1px solid #00baff; }
.tag-red { background: rgba(255,77,79,0.2); color: #ff4d4f; border: 1px solid #ff4d4f; }
.tag-green { background: rgba(82,196,26,0.2); color: #52c41a; border: 1px solid #52c41a; }
.tag-yellow { background: rgba(250,173,20,0.2); color: #faad14; border: 1px solid #faad14; }
.tag-cyan { background: rgba(19,194,194,0.2); color: #13c2c2; border: 1px solid #13c2c2; }
.tag-dark { background: rgba(200,200,200,0.2); color: #fff; border: 1px solid #aaa; }
</style>
