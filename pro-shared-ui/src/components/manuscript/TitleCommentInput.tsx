import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type InputHTMLAttributes,
  type MouseEvent,
  type UIEvent,
} from "react";
import {
  buildTitleCommentOverlayTokens,
  titleCommentIdsAtOffset,
  type TitleCommentHighlight,
} from "./titleCommentHighlights";

export type { TitleCommentHighlight } from "./titleCommentHighlights";

export interface TitleCommentInputProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "aria-label" | "children" | "style" | "type" | "value"
> {
  value: string;
  highlights: readonly TitleCommentHighlight[];
  ariaLabel: string;
  containerStyle?: CSSProperties;
  inputStyle?: CSSProperties;
  onCommentActivate?: (commentIds: number[], event: MouseEvent<HTMLInputElement>) => void;
}

const titleMetrics: CSSProperties = {
  boxSizing: "border-box",
  width: "100%",
  minWidth: 0,
  border: "none",
  borderBottom: "1px solid transparent",
  padding: 0,
  fontFamily: "'Courier Prime',monospace",
  fontSize: 15,
  fontWeight: 700,
  letterSpacing: ".02em",
  lineHeight: 1.2,
};

/**
 * An editable native input with a non-interactive, range-accurate comment layer.
 * The real text, selection, caret, IME, and screen-reader semantics stay owned by
 * the input. The layer underneath contributes only background/underline paint.
 */
export const TitleCommentInput = forwardRef<HTMLInputElement, TitleCommentInputProps>(function TitleCommentInput({
  value,
  highlights,
  ariaLabel,
  containerStyle,
  inputStyle,
  onClick,
  onCommentActivate,
  onScroll,
  ...inputProps
}, forwardedRef) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [scrollLeft, setScrollLeft] = useState(0);
  const tokens = useMemo(
    () => buildTitleCommentOverlayTokens(value, highlights),
    [highlights, value],
  );

  useImperativeHandle(forwardedRef, () => inputRef.current as HTMLInputElement, []);

  const syncScroll = useCallback(() => {
    setScrollLeft(inputRef.current?.scrollLeft ?? 0);
  }, []);

  useLayoutEffect(() => {
    syncScroll();
  }, [syncScroll, value]);

  const handleScroll = (event: UIEvent<HTMLInputElement>) => {
    setScrollLeft(event.currentTarget.scrollLeft);
    onScroll?.(event);
  };

  const handleClick = (event: MouseEvent<HTMLInputElement>) => {
    onClick?.(event);
    if (event.defaultPrevented) return;
    const from = event.currentTarget.selectionStart;
    const to = event.currentTarget.selectionEnd;
    if (from == null || to == null || from !== to) return;
    const commentIds = titleCommentIdsAtOffset(highlights, from);
    if (commentIds.length) onCommentActivate?.(commentIds, event);
  };

  return (
    <span
      data-title-comment-input
      style={{
        position: "relative",
        display: "grid",
        flex: 1,
        minWidth: 0,
        ...containerStyle,
      }}
    >
      <span
        aria-hidden="true"
        data-title-comment-overlay
        style={{
          gridArea: "1 / 1",
          position: "relative",
          zIndex: 0,
          minWidth: 0,
          overflow: "hidden",
          pointerEvents: "none",
          userSelect: "none",
          ...titleMetrics,
          color: "transparent",
          whiteSpace: "pre",
        }}
      >
        <span
          style={{
            display: "inline-block",
            minWidth: "100%",
            transform: `translateX(${-scrollLeft}px)`,
          }}
        >
          {tokens.map((token, index) => {
            if (token.kind === "point") {
              return (
                <span key={`point-${token.fromOffset}-${token.commentIds.join("-")}-${index}`} style={{ display: "inline-block", position: "relative", width: 0 }}>
                  <span
                    data-title-comment-point
                    data-comment-ids={token.commentIds.join(",")}
                    data-comment-resolved={token.resolved ? "true" : "false"}
                    style={{
                      position: "absolute",
                      left: -1,
                      bottom: 0,
                      width: 2,
                      height: "1.2em",
                      background: token.resolved ? "rgba(255,190,61,.38)" : "var(--amber)",
                    }}
                  />
                </span>
              );
            }
            if (!token.commentIds.length) {
              return <span key={`text-${token.fromOffset}`}>{token.text}</span>;
            }
            return (
              <span
                key={`range-${token.fromOffset}-${token.toOffset}`}
                data-title-comment-range
                data-comment-ids={token.commentIds.join(",")}
                data-comment-resolved={token.resolved ? "true" : "false"}
                style={{
                  background: token.resolved ? "rgba(255,190,61,.10)" : "rgba(255,190,61,.22)",
                  boxShadow: token.resolved
                    ? "inset 0 -1px 0 rgba(255,190,61,.48)"
                    : "inset 0 -1px 0 var(--amber)",
                }}
              >
                {token.text}
              </span>
            );
          })}
        </span>
      </span>
      <input
        {...inputProps}
        ref={inputRef}
        type="text"
        value={value}
        aria-label={ariaLabel}
        onClick={handleClick}
        onScroll={handleScroll}
        style={{
          gridArea: "1 / 1",
          position: "relative",
          zIndex: 1,
          ...titleMetrics,
          background: "transparent",
          outline: "none",
          color: "var(--strong)",
          ...inputStyle,
        }}
      />
    </span>
  );
});
