<template>
  <div class="chart-container" ref="chartRef"></div>
</template>

<script setup>
/**
 * `platformCountData` → ECharts 柱图；`activePlatform` 命中柱体套红渐变（与榜单同源高亮）。
 */
import { ref, onMounted, onUnmounted, watch } from 'vue';
import * as echarts from 'echarts';
import { useSentinelStore } from '../stores/sentinelStore';

const store = useSentinelStore();
const chartRef = ref(null);
let myChart = null;
const noDataPlatforms = ['暂无数据'];
const handleResize = () => {
  if (myChart) myChart.resize();
};

const renderChart = () => {
  if (!myChart) return;

  const platforms = Object.keys(store.platformCountData || {});
  const hasData = platforms.length > 0;
  const visiblePlatforms = hasData ? platforms : noDataPlatforms;

  const seriesData = visiblePlatforms.map(plat => {
    if (!hasData) return 0;
    const isTarget = plat === store.activePlatform;
    return {
      value: store.platformCountData[plat],
      itemStyle: isTarget ? {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#ff4d4f' },
          { offset: 1, color: '#ff7675' }
        ]),
        shadowBlur: 20,
        shadowColor: 'rgba(255, 77, 79, 0.8)'
      } : null,
      label: isTarget ? { show: true, position: 'top', color: '#ff4d4f', fontSize: 18, fontWeight: 'bold' } : { show: true, position: 'top', color: '#00baff' }
    };
  });

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(5, 23, 43, 0.92)',
      borderColor: 'rgba(0, 229, 255, 0.45)',
      textStyle: { color: '#d7f6ff' },
      axisPointer: { type: 'shadow' }
    },
    grid: { left: '3%', right: '4%', bottom: '5%', top: '15%', containLabel: true },
    xAxis: {
      type: 'category',
      data: visiblePlatforms,
      axisLabel: { color: '#a7d3ef', interval: 0, rotate: 24, fontSize: 12 },
      axisLine: { lineStyle: { color: 'rgba(0, 186, 255, 0.45)' } }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#a7d3ef' },
      splitLine: { lineStyle: { color: 'rgba(0, 186, 255, 0.1)', type: 'dashed' } },
      minInterval: 1
    },
    series: [
      {
        name: '涉及灰产线索数',
        type: 'bar',
        barWidth: '42%',
        data: seriesData,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#15ecff' },
            { offset: 1, color: '#1a5ee8' }
          ]),
          borderRadius: [6, 6, 0, 0],
          shadowBlur: 12,
          shadowColor: 'rgba(21, 236, 255, 0.3)'
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 20,
            shadowColor: 'rgba(21, 236, 255, 0.6)'
          }
        }
      }
    ]
  };
  myChart.setOption(option, true);
};

onMounted(() => {
  myChart = echarts.init(chartRef.value);
  renderChart();
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  if (myChart) myChart.dispose();
});

watch([() => store.platformCountData, () => store.activePlatform], () => {
  renderChart();
}, { deep: true });

</script>

<style scoped>
.chart-container { width: 100%; height: 100%; }
</style>
