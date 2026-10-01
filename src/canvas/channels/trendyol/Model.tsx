import ModelPage from '../marketplace/ModelPage';
import { TrendyolFrame } from './parts';

/** Aşama 0: Trendyol satış modeli Logo'dan ölçülür (tahmin yok). */
export default function TrendyolModel() {
  return <ModelPage platform="trendyol" Frame={TrendyolFrame} />;
}
