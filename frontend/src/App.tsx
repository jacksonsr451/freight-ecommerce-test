import { Navigate, Route, Routes } from 'react-router-dom';
import Shell from './components/Shell';
import CatalogPage from './pages/CatalogPage';
import CartPage from './pages/CartPage';
import CheckoutPage from './pages/CheckoutPage';
import DiagnosticsPage from './pages/DiagnosticsPage';
import OrdersPage from './pages/OrdersPage';
import OrderPage from './pages/OrderPage';
import NotFoundPage from './pages/NotFoundPage';
import ProductPage from './pages/ProductPage';
import AdminOrdersPage from './pages/AdminOrdersPage';

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/catalogo" replace />} />
        <Route path="catalogo" element={<CatalogPage />} />
        <Route path="catalogo/:productId" element={<ProductPage />} />
        <Route path="carrinho" element={<CartPage />} />
        <Route path="checkout" element={<CheckoutPage />} />
        <Route path="pedidos" element={<OrdersPage />} />
        <Route path="pedidos/:orderId" element={<OrderPage />} />
        <Route path="admin/pedidos" element={<AdminOrdersPage />} />
        <Route path="diagnostico" element={<DiagnosticsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
