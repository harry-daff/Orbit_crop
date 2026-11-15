import { X } from 'lucide-react'

export default function ClearableInput({ value, onChange, onClear, className = '', clearLabel = 'Clear input', ...props }) {
  const hasValue = value != null && String(value).length > 0
  return <div className="relative min-w-0">
    <input {...props} value={value} onChange={onChange} className={`form-input pr-9 ${className}`}/>
    {hasValue && <button type="button" onClick={onClear} aria-label={clearLabel} title={clearLabel} className="absolute right-2 top-1/2 z-10 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full text-[#879387] hover:bg-[#eef2e9] hover:text-ink focus:outline-none focus:ring-2 focus:ring-field"><X size={14}/></button>}
  </div>
}
