import { useState } from 'react';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';

export function useUpload(portfolioId: string, refetch: () => void) {
    const [isUploading, setIsUploading] = useState(false);
    const [uploadError, setUploadError] = useState('');
    const [uploadSuccess, setUploadSuccess] = useState('');
    const [uploadRowErrors, setUploadRowErrors] = useState<any[]>([]);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [pdfPassword, setPdfPassword] = useState('');

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setUploadError('');
        setUploadSuccess('');
        setSelectedFile(file);
        setPdfPassword('');

        if (file.name.toLowerCase().endsWith('.csv')) {
            await processUpload(file, '');
        }
    };

    const processUpload = async (file: File, password?: string) => {
        setIsUploading(true);
        setUploadError('');
        setUploadSuccess('');
        setUploadRowErrors([]);

        const formData = new FormData();
        formData.append('file', file);
        if (password) {
            formData.append('password', password);
        }

        try {
            const res = await api.post(`/portfolios/${portfolioId}/upload`, formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            setUploadSuccess(res.data.message);
            setSelectedFile(null);
            setPdfPassword('');
            refetch(); // Refresh analytics after upload
        } catch (err: any) {
            if (err.response?.status === 422 && err.response.data?.detail?.errors) {
                setUploadError("Validation failed. Please correct the errors in your file.");
                setUploadRowErrors(err.response.data.detail.errors);
            } else {
                setUploadError(getErrorMessage(err, 'Upload failed. Please try again.'));
            }
        } finally {
            setIsUploading(false);
        }
    };

    return {
        isUploading,
        uploadError,
        uploadSuccess,
        uploadRowErrors,
        selectedFile,
        pdfPassword,
        setPdfPassword,
        handleFileSelect,
        processUpload
    };
}
