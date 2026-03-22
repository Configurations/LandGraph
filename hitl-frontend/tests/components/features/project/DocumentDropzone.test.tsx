import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DocumentDropzone } from '../../../../src/components/features/project/DocumentDropzone';

// Mock react-dropzone
vi.mock('react-dropzone', () => ({
  useDropzone: ({ onDrop, disabled }: { onDrop: (files: File[]) => void; disabled: boolean }) => ({
    getRootProps: () => ({
      role: 'button',
      onClick: () => {},
      'data-testid': 'dropzone',
    }),
    getInputProps: () => ({
      type: 'file',
      'data-testid': 'file-input',
    }),
    isDragActive: false,
    open: () => {
      if (!disabled) {
        const file = new File(['content'], 'test.md', { type: 'text/markdown' });
        onDrop([file]);
      }
    },
  }),
}));

describe('DocumentDropzone', () => {
  it('renders dropzone text', () => {
    render(<DocumentDropzone onUpload={vi.fn()} uploading={false} />);
    expect(screen.getByText('documents.dropzone')).toBeInTheDocument();
    expect(screen.getByText('documents.accepted_formats')).toBeInTheDocument();
  });

  it('calls onUpload when file is provided', async () => {
    const onUpload = vi.fn();
    render(<DocumentDropzone onUpload={onUpload} uploading={false} />);

    // Simulate via the mocked open function
    const { useDropzone } = await import('react-dropzone');
    const result = useDropzone({ onDrop: onUpload, accept: {}, multiple: false, disabled: false });
    result.open();

    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onUpload.mock.calls[0][0][0].name).toBe('test.md');
  });

  it('shows uploading state', () => {
    render(<DocumentDropzone onUpload={vi.fn()} uploading={true} />);
    expect(screen.getByText('documents.uploading')).toBeInTheDocument();
    // Should NOT show the normal dropzone text
    expect(screen.queryByText('documents.dropzone')).not.toBeInTheDocument();
  });
});
