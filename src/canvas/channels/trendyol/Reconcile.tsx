import ReconPage from '../marketplace/ReconPage';
import { TrendyolFrame } from './parts';

/** Aşama 1: Trendyol sipariş/iade ↔ Logo faturası mutabakatı ve hakediş. */
export default function TrendyolReconcile() {
  return <ReconPage platform="trendyol" Frame={TrendyolFrame} ordersLink="/trendyol/yukle" />;
}
