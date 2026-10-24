import { Box } from '@mui/material';
import type {
  ExpressionSpecification,
  GeoJSONSource,
  LayerSpecification,
  Map as MapLibreMap,
  MapLayerMouseEvent,
  MapMouseEvent,
} from 'maplibre-gl';
import maplibregl from 'maplibre-gl';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { shallow } from 'zustand/shallow';
import type { Assessment, Heatmap, RouteSet } from '../api/types';
import {
  EMPTY,
  boundsOf,
  cellFeatures,
  checkpointFeatures,
  positionAtElapsed,
  routeFeatures,
  routeMidpoint,
  segmentFeatures,
} from '../lib/geo';
import { cellColor, cellOpacity, riskColor } from '../lib/mapStyle';
import { useAppStore } from '../store';
import { CheckpointCard } from './CheckpointCard';
import { RouteChip } from './RouteChip';

const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron';
const INTERACTIVE = ['checkpoints', 'routes-hit'];
const ROUND = { 'line-cap': 'round', 'line-join': 'round' } as const;
const zoomWidth = (atZoom4: number, atZoom10: number): ExpressionSpecification => [
  'interpolate',
  ['linear'],
  ['zoom'],
  4,
  atZoom4,
  10,
  atZoom10,
];
const TRUCK_SVG =
  '<svg viewBox="0 0 24 24" width="16" height="16" fill="#fff" aria-hidden="true"><path d="M20 8h-3V4H3c-1.1 0-2 .9-2 2v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5zM6 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5m13.5-9 1.96 2.5H17V9.5zM18 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5"/></svg>';

function setData(map: MapLibreMap, id: string, data: GeoJSON.FeatureCollection) {
  (map.getSource(id) as GeoJSONSource | undefined)?.setData(data);
}

/** Every source and layer is created once; afterwards only data, filters and paint change. */
function addLayers(map: MapLibreMap) {
  for (const id of ['cells', 'routes', 'segments', 'checkpoints']) {
    map.addSource(id, { type: 'geojson', data: EMPTY, tolerance: 0.5 });
  }
  // Data sits under the basemap's place labels so town names stay readable.
  const labels = map.getStyle().layers?.find((layer) => layer.type === 'symbol')?.id;
  const layers: LayerSpecification[] = [
    {
      id: 'cells',
      type: 'fill',
      source: 'cells',
      paint: {
        'fill-color': cellColor(0),
        'fill-opacity': cellOpacity(0),
        'fill-antialias': false,
      },
    },
    {
      id: 'routes-other',
      type: 'line',
      source: 'routes',
      layout: ROUND,
      paint: { 'line-color': '#4b5563', 'line-opacity': 0.6, 'line-width': zoomWidth(2.5, 6) },
    },
    {
      id: 'route-casing',
      type: 'line',
      source: 'routes',
      filter: ['==', ['get', 'id'], ''],
      layout: ROUND,
      paint: { 'line-color': '#14181f', 'line-width': zoomWidth(6.5, 12) },
    },
    {
      id: 'route-selected',
      type: 'line',
      source: 'routes',
      filter: ['==', ['get', 'id'], ''],
      layout: ROUND,
      paint: { 'line-color': '#ffffff', 'line-width': zoomWidth(3.5, 8) },
    },
    {
      id: 'segments',
      type: 'line',
      source: 'segments',
      filter: ['==', ['get', 'routeId'], ''],
      layout: ROUND,
      paint: { 'line-color': riskColor(['get', 'level']), 'line-width': zoomWidth(3.5, 8) },
    },
  ];
  for (const layer of layers) map.addLayer(layer, labels);
  map.addLayer({
    id: 'routes-hit',
    type: 'line',
    source: 'routes',
    paint: { 'line-color': '#000', 'line-opacity': 0, 'line-width': 18 },
  });
  map.addLayer({
    id: 'checkpoints',
    type: 'circle',
    source: 'checkpoints',
    paint: {
      'circle-color': riskColor(['get', 'level']),
      'circle-radius': 2.5,
      'circle-stroke-color': '#14181f',
      'circle-stroke-width': 0.5,
    },
  });
}

interface Props {
  routeSet: RouteSet | null;
  assessment?: Assessment;
  heatmap?: Heatmap;
  recommendedId: string | null;
  forecastStartMs: number;
}

export function MapView({ routeSet, assessment, heatmap, recommendedId, forecastStartMs }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [chips, setChips] = useState<{ id: string; node: HTMLDivElement }[]>([]);
  const selectedRouteId = useAppStore((s) => s.selectedRouteId);
  const selectRoute = useAppStore((s) => s.selectRoute);
  const openCheckpoint = useAppStore((s) => s.openCheckpoint);
  const checkpointRef = useAppStore((s) => s.checkpoint);
  const popupNode = useMemo(() => document.createElement('div'), []);

  // Create the map once.
  useEffect(() => {
    const container = containerRef.current!;
    const map = new maplibregl.Map({
      container,
      style: STYLE_URL,
      center: [-98.5, 39.5],
      zoom: 3.3,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    map.on('load', () => {
      addLayers(map);
      setReady(true);
    });
    const resize = new ResizeObserver(() => map.resize());
    resize.observe(container);
    mapRef.current = map;
    if (import.meta.env.DEV) Object.assign(window, { __map: map });
    return () => {
      resize.disconnect();
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

  // Routes: draw as soon as the route set arrives, and frame them.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setData(map, 'routes', routeSet ? routeFeatures(routeSet.routes) : EMPTY);
    if (routeSet) {
      map.fitBounds(boundsOf(routeSet.routes), {
        padding: { top: 80, bottom: 170, left: 60, right: 60 },
        duration: 700,
        maxZoom: 11,
      });
    }
  }, [ready, routeSet]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setData(map, 'segments', assessment ? segmentFeatures(assessment) : EMPTY);
    setData(map, 'checkpoints', assessment ? checkpointFeatures(assessment) : EMPTY);
  }, [ready, assessment]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setData(map, 'cells', heatmap ? cellFeatures(heatmap) : EMPTY);
  }, [ready, heatmap]);

  // Selection only swaps filters and paint expressions.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const id = selectedRouteId ?? '';
    map.setFilter('routes-other', ['!=', ['get', 'id'], id]);
    map.setFilter('route-casing', ['==', ['get', 'id'], id]);
    map.setFilter('route-selected', ['==', ['get', 'id'], id]);
    map.setFilter('segments', ['==', ['get', 'routeId'], id]);
    const onSelected: ExpressionSpecification = ['==', ['get', 'routeId'], id];
    // Zoom must be the outermost expression, so the selection test goes inside each stop.
    map.setPaintProperty('checkpoints', 'circle-radius', [
      'interpolate',
      ['linear'],
      ['zoom'],
      4,
      ['case', onSelected, 4.5, 2.5],
      10,
      ['case', onSelected, 7, 3.5],
    ]);
    map.setPaintProperty('checkpoints', 'circle-stroke-width', ['case', onSelected, 1.5, 0.5]);
    map.setLayoutProperty('checkpoints', 'circle-sort-key', ['case', onSelected, 1, 0]);
  }, [ready, selectedRouteId]);

  // The forecast slider never re-renders this component: it is applied straight to the map,
  // at most once per animation frame.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    let frame = 0;
    const apply = () => {
      frame = 0;
      const hour = useAppStore.getState().hour;
      map.setPaintProperty('cells', 'fill-color', cellColor(hour));
      map.setPaintProperty('cells', 'fill-opacity', cellOpacity(hour));
    };
    apply();
    const unsubscribe = useAppStore.subscribe(
      (s) => s.hour,
      () => {
        if (!frame) frame = requestAnimationFrame(apply);
      },
    );
    return () => {
      unsubscribe();
      cancelAnimationFrame(frame);
    };
  }, [ready]);

  // Truck marker: where the selected route puts the driver at the slider's hour.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !routeSet) return;
    const node = document.createElement('div');
    node.innerHTML = TRUCK_SVG;
    node.title = 'Truck position at the selected forecast hour';
    Object.assign(node.style, {
      width: '30px',
      height: '30px',
      borderRadius: '50%',
      background: '#14181f',
      border: '2px solid #fff',
      boxShadow: '0 1px 6px rgba(0,0,0,.35)',
      display: 'grid',
      placeItems: 'center',
    });
    const marker = new maplibregl.Marker({ element: node });
    const departureMs = Date.parse(routeSet.departure_utc);
    let shown = false;
    let frame = 0;
    const update = () => {
      frame = 0;
      const { hour, selectedRouteId: id } = useAppStore.getState();
      const route = routeSet.routes.find((r) => r.id === id);
      const elapsedS = (forecastStartMs + hour * 3_600_000 - departureMs) / 1000;
      const position = route ? positionAtElapsed(route, elapsedS) : null;
      if (position) {
        marker.setLngLat(position);
        if (!shown) marker.addTo(map);
        shown = true;
      } else if (shown) {
        marker.remove();
        shown = false;
      }
    };
    update();
    const unsubscribe = useAppStore.subscribe(
      (s) => [s.hour, s.selectedRouteId] as const,
      () => {
        if (!frame) frame = requestAnimationFrame(update);
      },
      { equalityFn: shallow },
    );
    return () => {
      unsubscribe();
      cancelAnimationFrame(frame);
      marker.remove();
    };
  }, [ready, routeSet, forecastStartMs]);

  // Summary chips at each route's midpoint (rendered by React through portals).
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !routeSet) {
      setChips([]);
      return;
    }
    const markers = routeSet.routes.map((route) => {
      const node = document.createElement('div');
      const marker = new maplibregl.Marker({ element: node, anchor: 'bottom', offset: [0, -8] })
        .setLngLat(routeMidpoint(route))
        .addTo(map);
      return { id: route.id, node, marker };
    });
    setChips(markers.map(({ id, node }) => ({ id, node })));
    return () => markers.forEach(({ marker }) => marker.remove());
  }, [ready, routeSet]);

  useEffect(() => {
    for (const chip of chips) chip.node.style.zIndex = chip.id === selectedRouteId ? '2' : '1';
  }, [chips, selectedRouteId]);

  // Clicks: checkpoints open a popup, route lines select the route, empty map closes the popup.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const onCheckpoint = (event: MapLayerMouseEvent) => {
      const props = event.features?.[0]?.properties as
        { routeId: string; index: number } | undefined;
      if (!props) return;
      const state = useAppStore.getState();
      if (state.selectedRouteId !== props.routeId) state.selectRoute(props.routeId);
      state.openCheckpoint({ routeId: props.routeId, index: props.index });
    };
    const onRoute = (event: MapLayerMouseEvent) => {
      if (map.queryRenderedFeatures(event.point, { layers: ['checkpoints'] }).length) return;
      const id = event.features?.[0]?.properties?.id as string | undefined;
      if (id) useAppStore.getState().selectRoute(id);
    };
    const onBackground = (event: MapMouseEvent) => {
      if (!map.queryRenderedFeatures(event.point, { layers: INTERACTIVE }).length) {
        useAppStore.getState().openCheckpoint(null);
      }
    };
    const pointer = () => (map.getCanvas().style.cursor = 'pointer');
    const reset = () => (map.getCanvas().style.cursor = '');
    map.on('click', 'checkpoints', onCheckpoint);
    map.on('click', 'routes-hit', onRoute);
    map.on('click', onBackground);
    for (const layer of INTERACTIVE) {
      map.on('mouseenter', layer, pointer);
      map.on('mouseleave', layer, reset);
    }
    return () => {
      map.off('click', 'checkpoints', onCheckpoint);
      map.off('click', 'routes-hit', onRoute);
      map.off('click', onBackground);
      for (const layer of INTERACTIVE) {
        map.off('mouseenter', layer, pointer);
        map.off('mouseleave', layer, reset);
      }
    };
  }, [ready]);

  const checkpoint =
    checkpointRef &&
    assessment?.routes.find((r) => r.id === checkpointRef.routeId)?.checkpoints[
      checkpointRef.index
    ];

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !checkpoint) return;
    const popup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      maxWidth: 'none',
      offset: 14,
      focusAfterOpen: false,
    })
      .setLngLat([checkpoint.lon, checkpoint.lat])
      .setDOMContent(popupNode)
      .addTo(map);
    return () => {
      popup.remove();
    };
  }, [ready, checkpoint, popupNode]);

  return (
    <>
      <Box
        ref={containerRef}
        sx={{ position: 'absolute', inset: 0 }}
        aria-label="Route map"
        role="region"
      />
      {checkpoint &&
        checkpointRef &&
        routeSet &&
        createPortal(
          <CheckpointCard
            checkpoint={checkpoint}
            routeId={checkpointRef.routeId}
            originTz={routeSet.origin_tz}
            onClose={() => openCheckpoint(null)}
          />,
          popupNode,
        )}
      {routeSet &&
        chips.map(({ id, node }) => {
          const route = routeSet.routes.find((r) => r.id === id);
          return (
            route &&
            createPortal(
              <RouteChip
                route={route}
                selected={id === selectedRouteId}
                recommended={id === recommendedId}
                onSelect={() => selectRoute(id)}
              />,
              node,
              id,
            )
          );
        })}
    </>
  );
}
