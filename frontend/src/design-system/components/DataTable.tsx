import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import {
  DataGrid,
  type GridColDef,
  type GridPaginationModel,
  type GridRowParams,
  type GridSortModel,
  type GridValidRowModel,
} from '@mui/x-data-grid';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { Page } from '@/api/client';
import { EmptyState } from './EmptyState';

export interface PageRequest {
  page: number;
  size: number;
  sort?: string;
}

export interface DataTableProps<T extends GridValidRowModel> {
  queryKey: readonly unknown[];
  fetchPage: (req: PageRequest) => Promise<Page<T>>;
  columns: GridColDef<T>[];
  getRowId?: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  toolbar?: ReactNode;
  initialSort?: GridSortModel;
  pageSizeOptions?: number[];
  emptyTitle?: string;
  emptyDescription?: string;
  height?: number | string;
}

export function sortParam(model: GridSortModel): string | undefined {
  const parts = model.map((s) => (s.sort === 'desc' ? `-${s.field}` : s.field));
  return parts.length ? parts.join(',') : undefined;
}

/**
 * Server-driven table: pagination and sorting happen in the API (never load everything into the
 * browser). Filtering is done by the caller through `queryKey`/`fetchPage`.
 */
export function DataTable<T extends GridValidRowModel>({
  queryKey,
  fetchPage,
  columns,
  getRowId,
  onRowClick,
  toolbar,
  initialSort = [],
  pageSizeOptions = [10, 25, 50, 100],
  emptyTitle,
  emptyDescription,
  height,
}: DataTableProps<T>) {
  const { t } = useTranslation();
  const [pagination, setPagination] = useState<GridPaginationModel>({ page: 0, pageSize: 25 });
  const [sort, setSort] = useState<GridSortModel>(initialSort);
  const request: PageRequest = { page: pagination.page + 1, size: pagination.pageSize, sort: sortParam(sort) };
  const { data, isFetching, isError } = useQuery({
    queryKey: [...queryKey, request],
    queryFn: () => fetchPage(request),
    placeholderData: keepPreviousData,
  });

  return (
    <Card>
      {toolbar && <Box sx={{ p: 2, pb: 0 }}>{toolbar}</Box>}
      <Box sx={{ height: height ?? 'auto', width: '100%' }}>
        <DataGrid<T>
          rows={data?.items ?? []}
          columns={columns}
          getRowId={getRowId}
          rowCount={data?.total ?? 0}
          loading={isFetching}
          paginationMode="server"
          sortingMode="server"
          filterMode="server"
          paginationModel={pagination}
          onPaginationModelChange={setPagination}
          sortModel={sort}
          onSortModelChange={(m) => {
            setSort(m);
            setPagination((p) => ({ ...p, page: 0 }));
          }}
          pageSizeOptions={pageSizeOptions}
          disableColumnFilter
          disableRowSelectionOnClick
          autoHeight={!height}
          onRowClick={onRowClick ? (p: GridRowParams<T>) => onRowClick(p.row) : undefined}
          slots={{
            noRowsOverlay: () => (
              <EmptyState
                title={isError ? t('errors.INTERNAL_ERROR') : (emptyTitle ?? t('common.noRecords'))}
                description={emptyDescription}
              />
            ),
          }}
          sx={{
            border: 0,
            '& .MuiDataGrid-row': { cursor: onRowClick ? 'pointer' : 'default' },
            '& .MuiDataGrid-columnHeaders': { bgcolor: 'action.hover' },
            '--DataGrid-overlayHeight': '220px',
          }}
          localeText={{ noRowsLabel: t('common.noRecords') }}
        />
      </Box>
    </Card>
  );
}
