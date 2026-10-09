export function money(cents: number) {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(cents / 100);
}
export function weight(grams: number) {
  return `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 3 }).format(grams / 1000)} kg`;
}
