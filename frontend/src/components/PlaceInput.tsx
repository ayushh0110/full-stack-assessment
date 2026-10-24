import { Autocomplete, Box, InputAdornment, TextField, Typography } from '@mui/material';
import type { ReactNode } from 'react';
import { useState } from 'react';
import { usePlaceSearch, useSlow } from '../api/hooks';
import type { Place } from '../api/types';

interface Props {
  label: string;
  icon: ReactNode;
  value: Place | null;
  onChange: (place: Place | null) => void;
  error?: string;
}

export function PlaceInput({ label, icon, value, onChange, error }: Props) {
  const [input, setInput] = useState('');
  const search = usePlaceSearch(input);
  const typedEnough = input.trim().length >= 3;
  const slow = useSlow(search.isFetching, 5000);

  return (
    <Autocomplete
      value={value}
      onChange={(_, place) => onChange(place)}
      inputValue={input}
      onInputChange={(_, text) => setInput(text)}
      options={typedEnough ? (search.data ?? []) : []}
      filterOptions={(options) => options}
      getOptionLabel={(place) => place.label}
      isOptionEqualToValue={(a, b) => a.lat === b.lat && a.lon === b.lon}
      loading={search.isFetching}
      loadingText={slow ? 'Waking up the server, this can take up to a minute…' : 'Searching…'}
      noOptionsText={
        !typedEnough
          ? 'Type at least 3 letters'
          : search.isError
            ? search.error.message
            : 'No places found'
      }
      autoHighlight
      renderOption={({ key, ...props }, place) => {
        const [name, ...rest] = place.label.split(', ');
        return (
          <Box component="li" key={key} {...props}>
            <Box>
              <Typography variant="body2" fontWeight={600}>
                {name}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {rest.join(', ')}
              </Typography>
            </Box>
          </Box>
        );
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          placeholder="City or address"
          error={Boolean(error)}
          helperText={error}
          slotProps={{
            input: {
              ...params.InputProps,
              startAdornment: <InputAdornment position="start">{icon}</InputAdornment>,
            },
          }}
        />
      )}
    />
  );
}
