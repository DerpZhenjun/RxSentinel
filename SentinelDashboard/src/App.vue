<template>
  <ScreenView />
</template>

<script setup>
// 单页壳：布局与轮询均在 ScreenView
import ScreenView from './views/ScreenView.vue'
</script>

<style>
/* 清边距、禁页面滚动；底色贴合 DataV 发光边框 */
html, body, #app {
  margin: 0;
  padding: 0;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background-color: #030409;
}
</style>
