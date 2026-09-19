/** echarts-gl tür bildirimi taşımıyor; alt yolları modül olarak tanıtır. */
/* eslint-disable @typescript-eslint/no-explicit-any */
declare module 'echarts-gl/charts' {
  export const Bar3DChart: any;
  export const SurfaceChart: any;
  export const Line3DChart: any;
  export const Scatter3DChart: any;
}
declare module 'echarts-gl/components' {
  export const Grid3DComponent: any;
  export const GlobeComponent: any;
}
