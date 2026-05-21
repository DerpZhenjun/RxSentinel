<template>
  <div class="screen-view" ref="screenRef">
    <div class="bg-grid"></div>
    <div class="bg-scanline"></div>
    <dv-border-box-11 title="RxSentinel 处方药灰产监控指挥中心" :titleWidth="450">

      <div class="fullscreen-btn" @click="toggleFullScreen">
        <span v-if="!isFullscreen">⛶ 全屏显示</span>
        <span v-else>🗗 退出全屏</span>
      </div>

      <div class="main-content">
        <div class="indicators-row">
          <TopIndicators />
        </div>
        <div class="system-status">
          <span v-if="store.isFetching">数据同步中...</span>
          <span v-else-if="store.fetchError" class="error-text">{{ store.fetchError }}</span>
          <span v-else>最近刷新：{{ store.lastRefreshAt || '初始化中' }} · {{ dataSourceHint }}</span>
        </div>
        <div class="panels-container">
          <div class="left-panel">
            <dv-border-box-13 class="panel-box">
              <div class="panel-title">平台灰产活跃度追踪</div>
              <div class="chart-wrapper">
                <PlatformChart />
              </div>
            </dv-border-box-13>
          </div>

          <div class="center-panel">
            <dv-border-box-8 :reverse="true" class="panel-box">
              <IntelligenceFeed />
            </dv-border-box-8>
          </div>

          <div class="right-panel">
            <dv-border-box-13 class="panel-box">
               <div class="panel-title">高危实体拦截 / 封禁榜</div>
               <div class="chart-wrapper">
                 <HighRiskRanking />
               </div>
            </dv-border-box-13>
          </div>
        </div>
      </div>
    </dv-border-box-11>
  </div>
</template>

<script setup>
/**
 * DataV 外框 + 左柱图 / 中流 / 右榜：`fetchAndParseData` 定时拉数；
 * `screenRef` 预留大屏缩放锚点。
 */
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useSentinelStore } from '../stores/sentinelStore';

import TopIndicators from '../components/TopIndicators.vue';
import PlatformChart from '../components/PlatformChart.vue';
import IntelligenceFeed from '../components/IntelligenceFeed.vue';
import HighRiskRanking from '../components/HighRiskRanking.vue';

const screenRef = ref(null);
const store = useSentinelStore();

const dataSourceHint = computed(() => {
  switch (store.dataMode) {
    case 'jsonl':
      return '数据源：extracted_channels.jsonl（本地）';
    case 'api':
      return '数据源：Mongo API';
    case 'error':
      return '数据源：不可用';
    default:
      return `数据源：${store.dataMode || '—'}`;
  }
});

const isFullscreen = ref(false);
const toggleFullScreen = () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(e => console.error(e));
  } else {
    if (document.exitFullscreen) document.exitFullscreen();
  }
};
const handleFullscreenChange = () => { isFullscreen.value = !!document.fullscreenElement; };

let fetchTimer = null;

onMounted(() => {
  document.addEventListener('fullscreenchange', handleFullscreenChange);
  store.fetchAndParseData();
  // 10s 轮询：与后端读路径升级频率大致同级，过长会像僵屏。
  fetchTimer = setInterval(() => store.fetchAndParseData(), 10000);
});

onUnmounted(() => {
  document.removeEventListener('fullscreenchange', handleFullscreenChange);
  if (fetchTimer) clearInterval(fetchTimer);
});
</script>

<style scoped>
.screen-view { width: 100vw; height: 100vh; padding: 15px; box-sizing: border-box; position: relative; background: radial-gradient(circle at 50% 20%, rgba(0, 186, 255, 0.12), transparent 40%), #030409; color: #fff; overflow: hidden; font-family: 'Microsoft YaHei', sans-serif; }
.bg-grid { position: absolute; inset: 0; pointer-events: none; opacity: 0.2; background-image: linear-gradient(rgba(0, 186, 255, 0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 186, 255, 0.08) 1px, transparent 1px); background-size: 42px 42px; }
.bg-scanline { position: absolute; left: 0; right: 0; height: 120px; background: linear-gradient(180deg, rgba(0, 186, 255, 0), rgba(0, 186, 255, 0.16), rgba(0, 186, 255, 0)); filter: blur(10px); animation: scan 8s linear infinite; pointer-events: none; }
.main-content { position: relative; z-index: 2; display: flex; flex-direction: column; height: calc(100% - 60px); min-height: 0; padding: 50px 20px 20px 20px; }
.indicators-row { flex: 0 0 72px; margin-bottom: 6px; min-height: 0; }
.system-status { flex: 0 0 22px; color: #8bbce6; font-size: 12px; margin-bottom: 8px; text-align: right; padding-right: 4px; text-shadow: 0 0 8px rgba(0, 186, 255, 0.4); }
.error-text { color: #ff7675; }
.panels-container { display: flex; justify-content: space-between; flex: 1; overflow: hidden; }
.left-panel, .right-panel { width: 26%; height: 100%; display: flex; flex-direction: column; }
.center-panel { width: 46%; height: 100%; }
.panel-box { width: 100%; height: 100%; }
.panel-title { text-align: center; padding-top: 15px; font-size: 16px; color: #00e5ff; font-weight: bold; letter-spacing: 2px; height: 40px; text-shadow: 0 0 10px rgba(0, 229, 255, 0.45); }
.chart-wrapper { width: 100%; height: calc(100% - 40px); padding: 10px; box-sizing: border-box; }

.fullscreen-btn { position: absolute; top: 25px; right: 30px; color: #00e5ff; font-size: 14px; cursor: pointer; z-index: 100; display: flex; align-items: center; padding: 5px 15px; border: 1px solid rgba(0, 186, 255, 0.45); border-radius: 4px; background: rgba(0, 186, 255, 0.08); transition: all 0.3s ease; user-select: none; backdrop-filter: blur(3px); }
.fullscreen-btn:hover { background: rgba(0, 186, 255, 0.2); border-color: #00e5ff; box-shadow: 0 0 14px rgba(0, 186, 255, 0.6); text-shadow: 0 0 6px #00baff; }

@keyframes scan {
  0% { transform: translateY(-140px); }
  100% { transform: translateY(calc(100vh + 140px)); }
}
</style>
