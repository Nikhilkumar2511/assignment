// Entry for the single-page build published as a Claude artifact (scripts/build-artifact.mjs).
import { createRoot } from "react-dom/client";
import Game from "../components/Game";

createRoot(document.getElementById("root")!).render(<Game />);
