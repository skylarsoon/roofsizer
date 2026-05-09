import { CheckCircle2 } from 'lucide-react';

export default function Toast({ visible, elapsed }) {
  return (
    <div className={visible ? 'toast toast-enter' : 'toast'} aria-live="polite">
      <CheckCircle2 size={15} color="#639922" strokeWidth={2.2} aria-hidden="true" />
      <span>Roof measured in {elapsed}s</span>
    </div>
  );
}
