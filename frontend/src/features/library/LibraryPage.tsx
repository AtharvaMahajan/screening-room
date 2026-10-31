import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { Button } from "../../components/Button";
import { Poster } from "../../components/Poster";
import { describeError } from "../../lib/errors";
import type { TitleCard } from "../titles/api";
import { type ListName, type MediaFilter, useLibraryChange, useLibraryList } from "./api";

const TABS: { name: ListName; label: string; empty: string }[] = [
  { name: "watchlist", label: "Watchlist", empty: "Nothing saved yet. Save titles from Discover." },
  { name: "history", label: "History", empty: "Nothing watched yet." },
  { name: "ratings", label: "Ratings", empty: "Nothing rated yet." },
  {
    name: "not-for-me",
    label: "Not for me",
    empty: "You haven't turned anything down. Titles you mark “not for me” show up here.",
  },
];
const FILTERS: { value: MediaFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "movie", label: "Movies" },
  { value: "tv", label: "TV" },
];

/** /library: watchlist, history, ratings and "not for me" (FR-12). Tab and filter live in the URL. */
export function LibraryPage() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.find((t) => t.name === params.get("tab")) ?? TABS[0];
  const media = FILTERS.find((f) => f.value === params.get("type"))?.value ?? "all";
  const choose = (next: { tab?: ListName; type?: MediaFilter }) => {
    const merged = { tab: tab?.name ?? "watchlist", type: media, ...next };
    setParams(merged.type === "all" ? { tab: merged.tab } : merged, { replace: true });
  };

  return (
    <div className="space-y-6 py-2">
      <h1 className="text-2xl font-semibold tracking-tight">Your library</h1>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <nav aria-label="Library lists" className="flex flex-wrap gap-1">
          {TABS.map((t) => (
            <Pill
              key={t.name}
              current={t.name === tab?.name}
              onClick={() => {
                choose({ tab: t.name });
              }}
            >
              {t.label}
            </Pill>
          ))}
        </nav>
        <div role="group" aria-label="Show" className="flex gap-1 text-sm">
          {FILTERS.map((f) => (
            <Pill
              key={f.value}
              current={f.value === media}
              onClick={() => {
                choose({ type: f.value });
              }}
            >
              {f.label}
            </Pill>
          ))}
        </div>
      </div>
      {tab && <List key={tab.name + media} name={tab.name} media={media} empty={tab.empty} />}
    </div>
  );
}

function List({ name, media, empty }: { name: ListName; media: MediaFilter; empty: string }) {
  const shell = { media, empty };
  switch (name) {
    case "watchlist":
      return <WatchlistList {...shell} />;
    case "history":
      return <HistoryList {...shell} />;
    case "ratings":
      return <RatingsList {...shell} />;
    case "not-for-me":
      return <NotForMeList {...shell} />;
  }
}

interface ShellProps {
  media: MediaFilter;
  empty: string;
}

function WatchlistList(props: ShellProps) {
  return (
    <ListShell query={useLibraryList("watchlist", props.media)} {...props}>
      {(items) =>
        items.map((item) => (
          <Row key={item.title.id} title={item.title} detail={`Saved ${day(item.added_at)}`}>
            <UndoButton titleId={item.title.id} kind="unsave" label={`Remove ${item.title.name}`}>
              Remove
            </UndoButton>
          </Row>
        ))
      }
    </ListShell>
  );
}

function HistoryList(props: ShellProps) {
  return (
    <ListShell query={useLibraryList("history", props.media)} {...props}>
      {(viewings) =>
        viewings.map((viewing) => (
          <Row
            key={viewing.id}
            title={viewing.title}
            detail={
              viewing.watched_on
                ? `Watched ${viewing.watched_on}`
                : `Marked watched ${day(viewing.created_at)}`
            }
          />
        ))
      }
    </ListShell>
  );
}

function RatingsList(props: ShellProps) {
  return (
    <ListShell query={useLibraryList("ratings", props.media)} {...props}>
      {(items) =>
        items.map((item) => (
          <Row key={item.title.id} title={item.title} detail={`Rated ${day(item.rated_at)}`}>
            <span aria-label={`${String(item.value)} out of 5 stars`} className="text-amber-500">
              {"★".repeat(item.value)}
              {"☆".repeat(5 - item.value)}
            </span>
          </Row>
        ))
      }
    </ListShell>
  );
}

function NotForMeList(props: ShellProps) {
  return (
    <ListShell query={useLibraryList("not-for-me", props.media)} {...props}>
      {(items) =>
        items.map((item) => (
          <Row key={item.title.id} title={item.title} detail={`Turned down ${day(item.marked_at)}`}>
            <UndoButton
              titleId={item.title.id}
              kind="undo_not_for_me"
              label={`Undo not for me for ${item.title.name}`}
            >
              Undo
            </UndoButton>
          </Row>
        ))
      }
    </ListShell>
  );
}

/** Loading, error and empty states for any list; `children` renders the items. */
function ListShell<Item>({
  query,
  media,
  empty,
  children,
}: ShellProps & {
  query: UseQueryResult<Item[]>;
  children: (items: Item[]) => ReactNode;
}) {
  if (query.isPending) {
    return <p className="text-stone-500">Loading…</p>;
  }
  if (query.isError) {
    return (
      <div className="space-y-3">
        <p role="alert">{describeError(query.error)}</p>
        <Button variant="quiet" onClick={() => void query.refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  if (query.data.length === 0) {
    return <p className="text-stone-500">{media === "all" ? empty : "Nothing here of that kind."}</p>;
  }
  return (
    <ul className="divide-y divide-stone-200 dark:divide-stone-800">{children(query.data)}</ul>
  );
}

function Row({
  title,
  detail,
  children,
}: {
  title: TitleCard;
  detail: string;
  children?: ReactNode;
}) {
  const href = `/titles/${String(title.id)}`;
  return (
    <li className="flex items-center gap-3 py-3">
      <Link to={href} tabIndex={-1} aria-hidden="true">
        <Poster url={title.poster_url} name={title.name} className="w-12" />
      </Link>
      <div className="min-w-0 flex-1">
        <Link to={href} className="font-medium hover:underline">
          {title.name}
        </Link>
        <p className="text-sm text-stone-500">
          {[title.media_type === "movie" ? "Movie" : "TV", title.year, detail]
            .filter((part) => part !== null)
            .join(" · ")}
        </p>
      </div>
      {children}
    </li>
  );
}

function UndoButton({
  titleId,
  kind,
  label,
  children,
}: {
  titleId: number;
  kind: "unsave" | "undo_not_for_me";
  label: string;
  children: string;
}) {
  const change = useLibraryChange(titleId);
  return (
    <Button
      variant="quiet"
      aria-label={label}
      disabled={change.isPending}
      onClick={() => {
        change.mutate({ kind });
      }}
    >
      {change.isError ? "Try again" : children}
    </Button>
  );
}

function Pill({
  current,
  onClick,
  children,
}: {
  current: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={current}
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-sm focus-visible:outline-2 focus-visible:outline-amber-600 ${
        current ? "bg-amber-600 text-white" : "hover:bg-stone-200 dark:hover:bg-stone-800"
      }`}
    >
      {children}
    </button>
  );
}

/** "2026-10-31T14:02:00Z" -> "Oct 31, 2026", in the user's time zone. */
function day(timestamp: string): string {
  return new Date(timestamp).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
