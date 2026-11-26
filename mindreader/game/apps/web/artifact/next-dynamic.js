// Stand-in for next/dynamic: React.lazy wrapped in Suspense.
export default function dynamic(loader) {
  const Lazy = window.React.lazy(() => loader().then((m) => ({ default: m.default ?? m })));
  return function Dynamic(props) {
    return window.React.createElement(window.React.Suspense, { fallback: null }, window.React.createElement(Lazy, props));
  };
}
