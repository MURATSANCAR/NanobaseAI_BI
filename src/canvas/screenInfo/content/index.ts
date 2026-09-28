import type { ScreenInfoMap } from '../types';
import analizFinans from './analiz-finans';
import editoryal from './editoryal';
import satisLojistik from './satis-lojistik';
import pazarlama from './pazarlama';
import seoGeo from './seo-geo';
import altyapi from './altyapi-ik-platform';

/** Bütün ekranların bilgi kutusu içeriği; Shell ilk kullanımda bu parçayı ayrı yükler. */
const CONTENT: ScreenInfoMap = {
  ...analizFinans,
  ...editoryal,
  ...satisLojistik,
  ...pazarlama,
  ...seoGeo,
  ...altyapi,
};

export default CONTENT;
