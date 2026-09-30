import ReconPage from '../marketplace/ReconPage';
import { AmazonFrame } from './parts';

/** Aşama 1: Amazon TR sipariş/iade ↔ Logo faturası mutabakatı ve hakediş. */
export default function AmazonReconcile() {
  return <ReconPage platform="amazon" Frame={AmazonFrame} />;
}
