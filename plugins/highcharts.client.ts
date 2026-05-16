import { defineNuxtPlugin } from '#app';
import Highcharts from 'highcharts';
import HighchartsVue from 'highcharts-vue';

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.use(HighchartsVue, {
    highcharts: Highcharts,
  });
});
