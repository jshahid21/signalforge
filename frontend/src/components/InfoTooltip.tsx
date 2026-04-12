/**
 * Info icon with hover/focus tooltip. Mobile-friendly via focus support.
 */
interface Props {
  text: string
}

export function InfoTooltip({ text }: Props) {
  return (
    <span className="relative inline-flex items-center group" data-testid="info-tooltip">
      <button
        type="button"
        className="ml-1 inline-flex items-center justify-center w-4 h-4 rounded-full text-gray-400 hover:text-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-400 cursor-help"
        aria-label={text}
        tabIndex={0}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="w-3.5 h-3.5"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0ZM8.94 6.94a.75.75 0 1 1-1.06-1.06 .75.75 0 0 1 1.06 1.06ZM10 8a.75.75 0 0 1 .75.75v4.5a.75.75 0 0 1-1.5 0v-4.5A.75.75 0 0 1 10 8Z"
            clipRule="evenodd"
          />
        </svg>
      </button>
      <span
        role="tooltip"
        className="invisible group-hover:visible group-focus-within:visible absolute left-1/2 -translate-x-1/2 top-full mt-1 z-50 w-48 rounded bg-gray-800 px-2.5 py-1.5 text-xs text-white shadow-lg pointer-events-none"
      >
        {text}
      </span>
    </span>
  )
}
