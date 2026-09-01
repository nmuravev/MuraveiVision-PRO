import type { MosaicNode } from 'react-mosaic-component';
import { convertLegacyToNary } from 'react-mosaic-component';
import type { ViewId } from './initialLayout';

/** Pure helpers for mosaic tree surgery (Premiere docking actions). */

type LegacySplit = {
  direction?: 'row' | 'column';
  first: MosaicNode<ViewId>;
  second: MosaicNode<ViewId>;
  splitPercentage?: number;
};

function isTabsNode(
  node: MosaicNode<ViewId>,
): node is Extract<MosaicNode<ViewId>, { type: 'tabs' }> {
  return typeof node === 'object' && node !== null && (node as { type?: string }).type === 'tabs';
}

function hasChildren(
  node: object,
): node is {
  type?: string;
  direction?: 'row' | 'column';
  children: MosaicNode<ViewId>[];
  splitPercentages?: number[];
} {
  return Array.isArray((node as { children?: unknown }).children);
}

function isLegacyBinary(node: object): node is LegacySplit {
  return (
    'first' in node &&
    'second' in node &&
    (node as LegacySplit).first != null &&
    (node as LegacySplit).second != null
  );
}

/** Normalize persisted / DnD trees (legacy first/second → n-ary). */
export function sanitizeMosaicTree(
  tree: MosaicNode<ViewId> | null,
): MosaicNode<ViewId> | null {
  if (tree == null) return null;
  try {
    return convertLegacyToNary(tree as MosaicNode<ViewId>);
  } catch {
    return tree;
  }
}

export function removeLeaf(
  node: MosaicNode<ViewId> | null,
  id: ViewId,
): MosaicNode<ViewId> | null {
  if (node === null) return null;
  if (typeof node === 'string') return node === id ? null : node;

  if (isTabsNode(node)) {
    const tabs = node.tabs.filter((t) => t !== id);
    if (tabs.length === 0) return null;
    if (tabs.length === 1) return tabs[0];
    return {
      ...node,
      tabs,
      activeTabIndex: Math.min(node.activeTabIndex, tabs.length - 1),
    };
  }

  const asObj = node as object;

  if (hasChildren(asObj)) {
    const children = asObj.children
      .map((c) => removeLeaf(c, id))
      .filter((c): c is MosaicNode<ViewId> => c !== null);
    if (children.length === 0) return null;
    if (children.length === 1) return children[0];
    return {
      type: 'split',
      direction: asObj.direction ?? 'row',
      children,
      splitPercentages: children.map(() => 100 / children.length),
    };
  }

  if (isLegacyBinary(asObj)) {
    const first = removeLeaf(asObj.first, id);
    const second = removeLeaf(asObj.second, id);
    if (!first && !second) return null;
    if (first && !second) return first;
    if (!first && second) return second;
    const pct = asObj.splitPercentage ?? 50;
    return {
      type: 'split',
      direction: asObj.direction ?? 'row',
      children: [first!, second!],
      splitPercentages: [pct, 100 - pct],
    };
  }

  // Unknown shape — do not crash
  return node;
}

export function dockAsSplit(
  tree: MosaicNode<ViewId> | null,
  id: ViewId,
  direction: 'row' | 'column' = 'row',
  percent = 70,
): MosaicNode<ViewId> {
  if (!tree) return id;
  return {
    type: 'split',
    direction,
    splitPercentages: [percent, 100 - percent],
    children: [tree, id],
  };
}

export function makeTabGroup(
  a: ViewId,
  b: ViewId,
  activeTabIndex = 0,
): MosaicNode<ViewId> {
  return { type: 'tabs', tabs: [a, b], activeTabIndex };
}
